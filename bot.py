import os
import discord
import dotenv
import requests 
import datetime
from discord.ext import commands, tasks
from discord.utils import get
from discord.ext.tasks import loop
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from io import BytesIO
from os import path

dotenv.load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Logging is done in Discord to this channel
LOGGER = int(os.getenv('LOGGER_ID'))

# Channel that logs are sent to
log = None

bot = commands.Bot(command_prefix='!')

# TODO: Create some sort of persistent storage in case the bot goes down.
#       Allow multiple Discord servers to use this bot (need to remember server id)
# Key:      Usernames
# Value:    Don't care
d = dict()

# Channel to post the killboard feed
ch = None

@bot.event
async def on_ready():
    global log

    log = bot.get_channel(LOGGER)
    await log.send('Killboard bot is up and running')

@bot.event
async def on_guild_join(guild):
    user = bot.get_user(guild.owner_id)

    await log.send(f'Joined {guild.name}')
    await user.send(f'Please register a channel in {guild.name} as the killboard with the !register command')

@bot.command(name='register', help='Register the current channel as the killboard')
@commands.has_role('admin')
async def register(ctx):
    global ch

    ch = ctx.channel.id
    channel = bot.get_channel(ch)
    
    await log.send(f'Channel {ctx.channel} ({ctx.channel.id}) has been registered as the killboard for {ctx.guild} ({ctx.guild.id})')
    await channel.send("The current channel has been registered as the killboard feed")
    
    killboard.start() 

# TODO: Modify to allow bulk adding of usernames
@bot.command(name='add', help='Add a username to watch')
@commands.has_role('admin')
async def add(ctx, name):
    username = name.lower()
    message = 'Successfully added ' + username
    if username in d:
        message = username + ' is already being watched'
    else:
        d[username] = 1

    await log.send(message)
    await ctx.send(message)

# TODO: Modify to allow bulk removal of usernames
@bot.command(name='remove', help='Stop watching a username')
@commands.has_role('admin')
async def remove(ctx, name):
    username = name.lower()
    message = f'Successfully removed {username}'
    if username in d:
        del d[username]
    else:
        message = f'{username} is already not being watched'

    await log.send(message)
    await ctx.send(message)

@bot.command(name='watching', help='Check which users are being watched')
@commands.has_role('admin')
async def watching(ctx):
    message = 'Currently watching:'
    for user in d:
        message += f'\n{user}'

    await log.send(message)
    await ctx.send(message)

# Actual Albion server logic YAY~~~

# API Endpoints
ALBION_EVENTS_URL = 'https://gameinfo.albiononline.com/api/gameinfo/events?limit=51&offset=0'
ALBION_IMAGE_URL = 'https://render.albiononline.com/v1/item/'
ALBION_KB_URL = 'https://albiononline.com/en/killboard/battles/'
IMAGES_PATH = 'assets/'
TEMPLATE_IMAGE = f'{IMAGES_PATH}template.png'
NEW_SIZE = 775      # Size of the item images
ITEMS_PER_ROW = 6
VICTIM_INV_TEXT_HEIGHT = 400   

# Killer equipment placements  
kLoc = [(-2020, -920), (-1245, -1010), (-470, -920), 
        (-2020, -225), (-1245, -320), (-470, -225),
        (-2020, 470), (-1245, 380), (-470, 470), 
        (-1245, 1080)]     

# Victim equipment placements
vLoc = [(485, -920), (1260, -1010), (2035, -920), 
        (485, -225), (1260, -320), (2035, -225),
        (485, 470), (1260, 380), (2035, 470), 
        (1260, 1080)]  

# Last event Id retrieved
eventId = 0

# Variable to remember whether the server is down
isDown = False

def getItemImage(item):
    if item is not None:
        itemURL = f'{ALBION_IMAGE_URL}{item["Type"]}.png?quality={item["Quality"]}'
        itemName = f'{item["Type"]}_{item["Quality"]}'.replace('@', '-')
        return (itemURL, item['Count'], itemName)
    return (None, None)

def getEquipment(equipment):
    l = list()
    l.append(getItemImage(equipment['Bag']))
    l.append(getItemImage(equipment['Head']))
    l.append(getItemImage(equipment['Cape']))
    l.append(getItemImage(equipment['MainHand']))
    l.append(getItemImage(equipment['Armor']))
    l.append(getItemImage(equipment['OffHand']))
    l.append(getItemImage(equipment['Food']))
    l.append(getItemImage(equipment['Shoes']))
    l.append(getItemImage(equipment['Potion']))
    l.append(getItemImage(equipment['Mount']))
    return l

def getInventory(inventory):
    l = list()
    for item in inventory:
        if item is not None:
            l.append(getItemImage(item))
    return l

def drawText(draw, text, font, x, y, w, h, center=True):
    wtext, htext = draw.textsize(text, font=font)
    xcoord = (w-wtext)/2 if center else w
    ycoord = (h-htext)/2 if center else h

    # Draw border
    draw.text((xcoord + x-5, ycoord + y-5), text, font=font, fill='black')
    draw.text((xcoord + x+5, ycoord + y-5), text, font=font, fill='black')
    draw.text((xcoord + x-5, ycoord + y+5), text, font=font, fill='black')
    draw.text((xcoord + x+5, ycoord + y+5), text, font=font, fill='black')

    # Draw text
    draw.text((xcoord + x, ycoord + y), text, font=font, fill='white')

def getItem(itemInfo, font):
    itemFile = f'{IMAGES_PATH}{itemInfo[2]}.png'

    # Check if file is already stored locally
    resized = None
    if os.path.exists(itemFile):
        print(f'{itemFile} exists!')
        resized = Image.open(itemFile)
    else:
        # Retrieve image and resize
        r = requests.get(itemInfo[0])

        # Skip this entire set of kills and try again on next event request
        if r.status_code != 200:
            print(f'Failed to get {itemInfo[0]}')
            return None

        im = Image.open(BytesIO(r.content))
        resized = im.resize((NEW_SIZE, NEW_SIZE))

        # Save the item to local storage
        print(f'Saving {itemFile}')
        resized.save(itemFile, 'PNG')

    # Add quantity text
    drawIcon = ImageDraw.Draw(resized)
    drawText(drawIcon, f'{itemInfo[1]}', font, 200, 175, NEW_SIZE, NEW_SIZE)

    return resized

def pasteEquips(img, equips, loc, font, w, h):
    for i, e in enumerate(equips):
        if e[0] is not None:
            resized = getItem(e, font)
            if resized is None:
                continue

            # Paste image
            img.paste(resized, ((w-NEW_SIZE)//2 + loc[i][0], (h-NEW_SIZE)//2 + loc[i][1])) 

# Execute this function 
@tasks.loop(seconds=10.0)
async def killboard():
    global eventId
    global isDown

    # Make request to the events api
    r = requests.get(ALBION_EVENTS_URL) 

    # Check the server status
    if r.status_code != 200:
        if not isDown:
            isDown = True
            await log.send(f'Albion events api is down as of {datetime.datetime.now()}')
        
        return
    
    if isDown:
        isDown = False
        await log.send(f'Albion events api is up again as of {datetime.datetime.now()}')

    # Convert the data to readable JSON
    data = r.json()
    
    # Iterate through the events
    for event in reversed(data):
        print(event['EventId'])
        if event['EventId'] <= eventId:
            print("This event has already been processed")
            continue

        # Check if killer.name or victim.name is in the dictionary
        killer = event['Killer']
        victim = event['Victim']

        if killer['Name'].lower() in d or victim['Name'].lower() in d:
            # Get basic info
            eventDateTime = event['TimeStamp'].split('T')
            eventDate = eventDateTime[0]
            eventTime = eventDateTime[1].split('.')[0]

            kAllyName = killer["AllianceName"] if killer["AllianceName"] else '-'
            kGuildName = killer["GuildName"] if killer["GuildName"] else '-'
            vAllyName = victim["AllianceName"] if victim["AllianceName"] else '-'
            vGuildName = victim["GuildName"] if victim["GuildName"] else '-'

            kIP = killer['AverageItemPower']
            vIP = victim['AverageItemPower']

            color = discord.Color.green() if killer['Name'].lower() in d else discord.Color.red()

            # Get assets
            print("Getting assets")
            kEquips = getEquipment(killer['Equipment'])
            vEquips = getEquipment(victim['Equipment'])
            vInventory = getInventory(victim['Inventory'])

            # Make the image
            print("Creating image...")
            outFile = f'{event["EventId"]}.png'
            img = Image.open(TEMPLATE_IMAGE)
            width, height = img.size

            # Make transparent image based on inventory size and template size
            # Space between items horizontally
            wItemSpace = (width - ITEMS_PER_ROW * NEW_SIZE) // (ITEMS_PER_ROW + 1) 

            # Number of inventory rows to add
            numRows = len(vInventory) // 6 + (len(vInventory) % 6 > 0)

            # Height of the transparent background
            hBackground = height + numRows*NEW_SIZE + (numRows > 0) * VICTIM_INV_TEXT_HEIGHT 

            #Transparent background
            imgBase = Image.new('RGBA', (width, hBackground), (255, 0, 0, 0))
            imgBase.paste(img)

            font = ImageFont.truetype('Arial Bold.ttf', 144) 
            # <victim>'s Inventory text placement
            if numRows > 0:
                drawBase = ImageDraw.Draw(imgBase)                     
                drawText(drawBase, f"{victim['Name']}'s Inventory", font, 2 * wItemSpace, 3000, 0, 0, False)

            # Add IP and fame
            print("Adding IP and fame text")
            draw = ImageDraw.Draw(imgBase)
            fontIcon = ImageFont.truetype('Arial Bold.ttf', 112)

            drawText(draw, f'IP: {int(kIP)}', font, -2025, 1125, width, height)
            drawText(draw, f'IP: {int(vIP)}', font, 2000, 1125, width, height)
            drawText(draw, f'{event["groupMemberCount"]} x {killer["KillFame"]}', font, 0, 1125, width, height)

            # Add equipment
            print("Adding equipment images")
            pasteEquips(imgBase, kEquips, kLoc, fontIcon, width, height)
            pasteEquips(imgBase, vEquips, vLoc, fontIcon, width, height)

            # Add inventory
            print("Adding inventory images")
            for i, item in enumerate(vInventory):
                # Height and width calculations
                row, col = i // 6, i % 6
                x = wItemSpace + col * (wItemSpace + NEW_SIZE)
                y = row * NEW_SIZE + height + VICTIM_INV_TEXT_HEIGHT

                resized = getItem(item, font)
                if resized is None: 
                    continue

                imgBase.paste(resized, (x, y)) 

            print('Saving killboard image')
            imgBase.save(outFile, 'PNG')

            print(f'{killer["Name"]}, {victim["Name"]}')

            # Locally stored images must be sent this way 
            imgfile = discord.File(outFile, filename=outFile)

            # Make the embed
            embed = discord.Embed(title=f'{killer["Name"]} killed {victim["Name"]}', url=f'{ALBION_KB_URL}{event["EventId"]}', color=color)
            embed.add_field(name=f'{kAllyName}', value=f'{kGuildName}', inline=True)
            embed.add_field(name=f'{vAllyName}', value=f'{vGuildName}', inline=True)
            embed.set_footer(text=f'{eventDate} {eventTime} UTC')
            embed.set_image(url=f'attachment://{outFile}')

            print("Sending killboard image")
            channel = bot.get_channel(ch)
            await channel.send(file=imgfile, embed=embed)
            
            # Delete the newly created image
            os.remove(outFile)

        eventId = event['EventId']

@killboard.before_loop
async def before_killboard():
    print('Waiting for bot to be ready...')
    await bot.wait_until_ready()
   
bot.run(TOKEN)
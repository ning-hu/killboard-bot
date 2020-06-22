# killboard-bot
Discord bot for the Albion Online killboard information to be displayed in a Discord channel

## Running the bot
```$ python3 bot.py```

## Environment Variables
`DISCORD_TOKEN`: Discord authentication token

`LOGGER_ID`: Id of the Discord channel designated as the logger

## Required Permissions
* Read Messages
* Send Messages
* Embed Links
* Send Files

`https://discord.com/api/oauth2/authorize?client_id=<your_client_id>&permissions=52224&scope=bot`

## Additional Information
Image assets are automatically stored to `assets/` when first retrieved. Sometimes, the images API is unresponsive, so this should speed things up when the same image is required in the future.

The person using commands must have the `admin` role in the Discord server.

If the bot goes down, all usernames that were watched will need to be re-added.

The bot makes an event api request every 10 seconds.

## TODO
* Make the tasks non-blocking
* Add a way to remember the watch list and re-create the in-memory watch list from it
* Add bulk adding/removing of people to watch
* Add an "ignore nakeds" option (no equips and no items in inventory)
* Add ability to watch guilds/alliances
* Refactor the Albion section of the code into a separate file

## Things I probably won't add
* Ability to use this bot with multiple guilds

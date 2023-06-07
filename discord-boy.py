import discord
from discord.ext import commands
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, time, timedelta
import asyncio


# Initialize Firebase Admin SDK
cred = credentials.Certificate("<CREDENTIALS>")
firebase_admin.initialize_app(cred)
db = firestore.client()


intents = discord.Intents.default()
intents.messages = True
intents.typing = False
intents.presences = False
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


#set cooldowns of 1 hour for static table generation

cooldown_mapping_games = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)

cooldown_mapping_dlc = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.change_presence(activity=discord.Game(name='!helpme'))


@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')


@bot.command()
async def helpme(ctx):
    embed = discord.Embed(title='Free to keep Steam games', color=discord.Color.dark_purple())

    # Set the headers of the table
    embed.add_field(name='!games', value='Shows a current list of free to keep steam games '
                                         '(Cooldown of 60 minutes per user)', inline=False)
    embed.add_field(name='!dlc', value='Shows a current list of free to keep steam DLCs'
                                       ' (Cooldown of 60 minutes per user)', inline=False)
    embed.add_field(name='!watchgames', value='Generates a single games table that will update itself every day with '
                                              'any new or outdated sales. Should only be used in a dedicated channel  '
                                              'to keep information visible. Can only be activate'
                                              ' in one channel for a server. (Will need to be run again after a bot '
                                              'update)', inline=False)
    embed.add_field(name='!stopwatchgames', value='used to stop an active instance of !watchgames', inline=False)

    # Set the footer
    embed.set_footer(text="Made for free-steam-games.vercel.app")

    await ctx.send(embed=embed)

#Static games table

@bot.command()
async def games(ctx):
    bucket = cooldown_mapping_games.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after:
        minutes = round(retry_after / 60)
        await ctx.send(f"Please wait {minutes} minutes before using this command again.")
        return

    embed = discord.Embed(title='Games', url="https://free-steam-games.vercel.app/", color=discord.Color.blue())

    embed.set_author(name="Free Steam Games", url="https://free-steam-games.vercel.app/",
                     icon_url=bot.user.avatar.url)

    # Create a query to fetch documents with is_free == True
    query = db.collection('games').where('is_free', '==', True)
    docs = query.get()

    # Check if any documents are found
    if not docs:
        await ctx.send('No free games today :(')  # Custom message when no games found
        return

    # Process the fetched documents
    for doc in docs:
        data = doc.to_dict()

        # Fetch specific fields and add them to the embed
        name = data.get('name')
        short_description = data.get('short_description')
        genres = ', '.join(data.get('genres', []))  # Join genres into a single string
        app_id = data.get('steam_appid')

        # Add fields to the embed
        embed.add_field(name='Name', value=f'[{name}](https://store.steampowered.com/app/{app_id})', inline=True)
        embed.add_field(name='Short Description', value=short_description, inline=True)
        embed.add_field(name='Genres', value=genres, inline=True)

        embed.set_footer(text="This is the current list of free to keep games.")

    await ctx.send(embed=embed)


@bot.command()
async def dlc(ctx):
    bucket = cooldown_mapping_dlc.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after:
        minutes = round(retry_after / 60)
        await ctx.send(f"Please wait {minutes} minutes before using this command again.")
        return

    embed = discord.Embed(title='DLC', url="https://free-steam-games.vercel.app/", color=discord.Color.dark_orange())

    embed.set_author(name="Free Steam Games", url="https://free-steam-games.vercel.app/",
                     icon_url=bot.user.avatar.url)

    # Create a query to fetch documents with is_free == True
    query = db.collection('dlc').where('is_free', '==', True)
    docs = query.get()

    # Check if any documents are found
    if not docs:
        await ctx.send('No free DLC today :(')  # Custom message when no games found
        return

    # Process the fetched documents
    for doc in docs:
        data = doc.to_dict()

        # Fetch specific fields and add them to the embed
        name = data.get('name')
        short_description = data.get('short_description')
        genres = ', '.join(data.get('genres', []))  # Join genres into a single string
        app_id = data.get('steam_appid')

        # Add fields to the embed
        embed.add_field(name='Name', value=f'[{name}](https://store.steampowered.com/app/{app_id})', inline=True)
        embed.add_field(name='Short Description', value=short_description, inline=True)
        embed.add_field(name='Genres', value=genres, inline=True)

        embed.set_footer(text="This is the current list of free to keep DLC.")

    await ctx.send(embed=embed)


is_watchgames_running = False  # Shared variable to track command status

@bot.command()
async def watchgames(ctx):
    global is_watchgames_running

    if is_watchgames_running:
        await ctx.send("The `watchgames` command is already running.")
        return

    is_watchgames_running = True

    try:
        # Generate the initial game table
        embed = await generate_games_table()

        # Post the table in the channel
        message = await ctx.send(embed=embed)

        # Get the channel ID from the message's channel
        channel_id = message.channel.id

        # Start updating the game table
        await update_games_table(ctx, channel_id)
    finally:
        is_watchgames_running = False


async def generate_games_table():
    embed = discord.Embed(title='Games', url="https://free-steam-games.vercel.app/", color=discord.Color.blue())

    embed.set_author(name="Free Steam Games", url="https://free-steam-games.vercel.app/",
                     icon_url=bot.user.avatar.url)

    # Create a query to fetch documents with is_free == True
    query = db.collection('games').where('is_free', '==', True)
    docs = query.get()

    # Check if any documents are found
    if not docs:
        embed.description = 'No free games today :('  # Custom message when no games found
        return embed

    # Process the fetched documents
    for doc in docs:
        data = doc.to_dict()

        # Fetch specific fields and add them to the embed
        name = data.get('name')
        short_description = data.get('short_description')
        genres = ', '.join(data.get('genres', []))  # Join genres into a single string
        app_id = data.get('steam_appid')

        # Add fields to the embed
        embed.add_field(name='Name', value=f'[{name}](https://store.steampowered.com/app/{app_id})', inline=True)
        embed.add_field(name='Short Description', value=short_description, inline=True)
        embed.add_field(name='Genres', value=genres, inline=True)

    embed.set_footer(text="This is the current list of free to keep games.")

    return embed


async def update_games_table(ctx, channel_id):
    target_time = time(hour=17, minute=2)  # Set to a minute after DB update, which is a minute after steam sales update

    while is_watchgames_running:
        now = datetime.utcnow().time()
        if now.hour == target_time.hour and now.minute == target_time.minute:
            # Fetch the updated game table from Firestore
            embed = await generate_games_table()

            # Get the channel object using the channel ID
            channel = bot.get_channel(channel_id)

            # Delete the existing message
            async for message in channel.history(limit=1):
                if message.author == bot.user:
                    await message.delete()
                    break

            # Send a new message with the updated table
            await channel.send(embed=embed)

            # Calculate the time until the next target time
            current_datetime = datetime.utcnow()
            next_target_datetime = datetime.combine(current_datetime.date(), target_time)
            if current_datetime > next_target_datetime:
                next_target_datetime += timedelta(days=1)
            sleep_time = (next_target_datetime - current_datetime).total_seconds()

            # Sleep until the next target time
            await asyncio.sleep(sleep_time)
        else:
            # If/else to prevent bot from skipping the current day if invoked before 17:02 UTC
            current_datetime = datetime.utcnow()
            next_target_datetime = datetime.combine(current_datetime.date(), target_time)
            if current_datetime > next_target_datetime:
                next_target_datetime += timedelta(days=1)
            sleep_time = (next_target_datetime - current_datetime).total_seconds()

            # Sleep until the next target time
            await asyncio.sleep(sleep_time)

# Helper Function to allow disabling !watchgames to prevent redundant updates in the same discord
@bot.command()
async def stopwatchgames(ctx):
    global is_watchgames_running

    if is_watchgames_running:
        is_watchgames_running = False
        await ctx.send("The `watchgames` command has been stopped.")
    else:
        await ctx.send("The `watchgames` command is not currently running.")


bot.run('<BOT KEY>')
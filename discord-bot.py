import discord
from discord.ext import commands
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, time, timedelta
import asyncio
from types import SimpleNamespace


# Initialize Firebase Admin SDK
<FIREBASE CREDENTIALS>
firebase_admin.initialize_app(cred)
db = firestore.client()


intents = discord.Intents.default()
intents.messages = True
intents.typing = False
intents.presences = False
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

cooldown_mapping_games = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)

cooldown_mapping_dlc = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.change_presence(activity=discord.Game(name='!helpme'))

    # Check Firestore for any running 'watchgames' commands
    docs = db.collection('watchgames').get()

    for doc in docs:
        guild_id = doc.id
        guild = bot.get_guild(int(guild_id))
        if guild:  # If the guild is found
            # Create a context-like object to pass to update_games_table
            ctx = SimpleNamespace()
            ctx.guild = guild
            ctx.channel = guild.get_channel(int(list(doc.get('channels').keys())[0]))  # Gets the first channel stored

            # Set is_watchgames_running to True and start the update_games_table task
            global is_watchgames_running
            is_watchgames_running = True
            bot.loop.create_task(update_games_table(ctx))  # Start the task in the event loop


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
                                              'to keep information visible. Can only be active for a single instance'
                                              ' in a server', inline=False)
    embed.add_field(name='!stopwatchgames', value='used to stop an active instance of !watchgames', inline=False)

    # Set the footer
    embed.set_footer(text="Made for free-steam-games.vercel.app")

    await ctx.send(embed=embed)


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

    # Check if the watchgames command is already running in the guild
    doc_ref = db.collection('watchgames').document(str(ctx.guild.id))
    doc = doc_ref.get()
    if doc.exists:
        await ctx.send("The `watchgames` command is already running in this guild.")
        return

    # Set the watchgames command as running in the guild and store the channel and message IDs
    message = await ctx.send("Watchgames command is running...")
    doc_ref.set({
        'channels': {
            str(ctx.channel.id): {
                'message_id': message.id
            }
        }
    })

    is_watchgames_running = True

    try:
        # Generate the initial game table
        embed = await generate_games_table()

        # Post the table in the channel
        await message.edit(embed=embed)

        # Start updating the game table
        await update_games_table(ctx)
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


async def update_games_table(ctx):
    target_time = time(hour=17, minute=48)  # Replace with your desired UTC time (e.g., 17:02)

    # Retrieve channel and message IDs from the Firestore database
    doc_ref = db.collection('watchgames').document(str(ctx.guild.id))
    doc = doc_ref.get()
    if not doc.exists:
        return

    channels = doc.get('channels')

    while is_watchgames_running:
        now = datetime.utcnow().time()
        if now.hour == target_time.hour and now.minute == target_time.minute:
            for channel_id, channel_data in channels.items():
                # Fetch the updated game table from Firestore
                embed = await generate_games_table()

                # Get the channel object using the channel ID
                channel = bot.get_channel(int(channel_id))

                if channel:
                    message_id = channel_data.get('message_id')

                    if message_id:
                        try:
                            # Fetch the message using the message ID
                            message = await channel.fetch_message(int(message_id))

                            # Delete the existing message
                            await message.delete()
                        except discord.NotFound:
                            pass

                    # Send a new message with the updated table
                    new_message = await channel.send(embed=embed)

                    # Update the message ID in the database
                    channels[channel_id]['message_id'] = str(new_message.id)

            doc_ref.update({
                'channels': channels
            })

            # Calculate the time until the next target time
            current_datetime = datetime.utcnow()
            next_target_datetime = datetime.combine(current_datetime.date(), target_time)
            if current_datetime > next_target_datetime:
                next_target_datetime += timedelta(days=1)
            sleep_time = (next_target_datetime - current_datetime).total_seconds()

            # Sleep until the next target time
            await asyncio.sleep(sleep_time)
        else:
            # Calculate the time until the next target time
            current_datetime = datetime.utcnow()
            next_target_datetime = datetime.combine(current_datetime.date(), target_time)
            if current_datetime > next_target_datetime:
                next_target_datetime += timedelta(days=1)
            sleep_time = (next_target_datetime - current_datetime).total_seconds()

            # Sleep until the next target time
            await asyncio.sleep(sleep_time)

@bot.command()
async def stopwatchgames(ctx):
    global is_watchgames_running

    # Check if the watchgames command is running in the guild
    doc_ref = db.collection('watchgames').document(str(ctx.guild.id))
    doc = doc_ref.get()
    if not doc.exists:
        await ctx.send("The `watchgames` command is not currently running in this guild.")
        return

    # Stop the watchgames command and remove the document from Firestore
    doc_ref.delete()
    is_watchgames_running = False
    await ctx.send("The `watchgames` command has been stopped.")
    
    <BOT CREDENTIALS>

# -*- coding: utf-8 -*-
from telegram.ext import Updater
from telegram.ext import CommandHandler
import logging
import requests
import settings
import dataset
from io import BytesIO
import pycurl
import json
import uuid

# Create the updater, dispatcher and job queue
updater = Updater(token=settings.api_token)
dispatcher = updater.dispatcher
jobqueue = updater.job_queue

# Set up logger
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
# Set up logging file handler
formatter = logging.Formatter('%(asctime)s - %(message)s')
handler = logging.FileHandler('nano_tipbot.log')
handler.setLevel(logging.INFO)
handler.setFormatter(formatter)
logger.addHandler(handler)

# Get the wallet from the local settings
wallet = settings.wallet

# Setup the initial Nano market statistics
nano_market_data = requests.get('https://api.coinmarketcap.com/v1/ticker/raiblocks/')
PriceInfo = nano_market_data.json()


# Routine to parse the request for the rai node and retrieve the response
def communicate_wallet(wallet_command):
    buffer = BytesIO()
    c = pycurl.Curl()
    c.setopt(c.URL, '[::1]')
    c.setopt(c.PORT, 7076)
    c.setopt(c.POSTFIELDS, json.dumps(wallet_command))
    c.setopt(c.WRITEFUNCTION, buffer.write)

    c.perform()

    c.close()

    body = buffer.getvalue()
    parsed_json = json.loads(body.decode('iso-8859-1'))
    return parsed_json


# Function to check if the username of a client has been registered in the database
def check_username(username):
    localdb = dataset.connect('sqlite:///' + settings.local_db_name)
    users_table = localdb['users']
    return users_table.find_one(user_id=username)


# Function to send an error stating that the user does not have a username.
def send_username_error(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text='Please set a username and try again. \n\n'
                                                          'Your username is used to authenticate access to your Tipbot wallet.')


def start(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text='Welcome to the Nano Telegram Tipbot!')
    help(bot, update)


def help(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text='The commands available are: \n\n'
                                                          '/help - Display this message \n'
                                                          '/price - Display current Nano market statistics \n'
                                                          '/register - Sign up for the Nano Tipbot \n'
                                                          '/balance - Check your Tipbot address balance \n'
                                                          '/deposit - Get your deposit address \n'
                                                          '/recover <recovery key> - Enter a recovery key to restore access to your account in the event of a username change \n'
                                                          '/tip <username> <amount> - Tip a user some Nano! They must already be registered on the Tipbot \n'
                                                          '/withdraw <address> <amount> - Withdraw your Tipbot funds to your personal wallet \n'
                                                          '/contribute - Find out how to contribute to the running of the Nano Tipbot')


def price(bot, update):
    # Display the currently storecd info from CoinMarketCap
    bot.send_message(chat_id=update.message.chat_id, text='The current Nano market statistics are: \n'
                                                          'Market Cap (USD): $' + PriceInfo[0]['market_cap_usd'] + '\n'
                                                          'Price (USD): $' + PriceInfo[0]['price_usd'] + '\n'
                                                          'Price (BTC): ' u'\u0243' + PriceInfo[0]['price_btc'] + '\n'
                                                          'Percent Change (24h): ' + PriceInfo[0]['percent_change_24h'] + '%')


def register(bot, update):
    # Attempt to fetch the username of the client
    client_username = str(update.message.from_user.username)
    if client_username == 'None':
        # If the username is 'None', the client has not set a username and thus cannot register
        send_username_error(bot, update)
    elif check_username(client_username):
        # If the user already exists in the database, they cannot register again
        bot.send_message(chat_id=update.message.chat_id, text='Your username is already registered! \n\n'
                                                              'Use /balance to check your balance.')
    else:
        # The client has a username and they are not yet registered, so begin the registration process
        # Connect to the database
        localdb = dataset.connect('sqlite:///' + settings.local_db_name)
        users_table = localdb['users']
        # Create account
        wallet_command = {'action': 'account_create', 'wallet': wallet}
        wallet_output = communicate_wallet(wallet_command)
        address = wallet_output['account']
        # Create recovery key (UUID4 token)
        recoverykey = str(uuid.uuid4())
        # Insert row containing username, account and recovery key into database
        logger.info('Registered user ' + client_username + ' with address ' + address + ' and recovery key ' + recoverykey)
        users_table.insert(dict(user_id=client_username, nano_address=str(address), recovery_key=recoverykey))
        # Notify the user
        bot.send_message(chat_id=update.message.chat_id, text='You have been registered! \n\n'
                                                              'Your deposit address is: ' + address + '\n\n'
                                                              'Your recovery key is: ' + recoverykey + '\n\n'
                                                              'Your username is your key to accessing your stored funds in the Nano Tipbot. '
                                                              'In order to avoid losing access to your funds or potential unauthorized access, please do not '
                                                              'change your username before withdrawing all funds.\n\n'
                                                              'Should you lose or change your username and lose access to your funds, please use /recover <recovery key> to authorize '
                                                              'an update to your stored username and restore access to your funds.\n\n'
                                                              'Use /balance to check your balance.')


def balance(bot, update):
    # Attempt to fetch the username of the client
    client_username = str(update.message.from_user.username)
    if client_username == 'None':
        # If the username is 'None', the client has not set a username and thus cannot register
        send_username_error(bot, update)
        return

    client_info = check_username(client_username)

    if not client_info:
        # If the user does not exist in the database they must register before checking their balance
        bot.send_message(chat_id=update.message.chat_id, text='You have not yet been registered for the Nano Tipbot.\n\n'
                                                              'Please use /register to sign up.')
    else:
        # The client has a valid username and they are already registered
        # Get address of client:
        address = client_info['xrb_address']
        # Get the account balance of the client:
        wallet_command = {'action': 'account_balance', 'account': address}
        wallet_output = communicate_wallet(wallet_command)
        wallet_command = {'action': 'rai_from_raw', 'amount': int(wallet_output['balance'])}
        rai_balance = communicate_wallet(wallet_command)
        nano_balance = format((float(rai_balance['amount']) / 1000000.0), '.6f')
        # Send the account balance in Nano to the user:
        bot.send_message(chat_id=update.message.chat_id, text='Your Nano Tipbot address is: \n\n' +
                                                              address + '\n\n'
                                                              'Your balance is: \n\n'
                                                              'Nano ' + str(nano_balance))


def recover(bot, update):
    # Attempt to fetch the username of the client
    client_username = str(update.message.from_user.username)
    client_info = check_username(client_username)

    if client_username == 'None':
        # If the username is 'None', the client has not set a username and thus cannot register
        send_username_error(bot, update)
    elif client_info:
        # If the user already exists in the database, notify them and show them their current recovery key.
        bot.send_message(chat_id=update.message.chat_id, text='Your username is already associated with an address on Nano Tipbot.\n\n'
                                                              'Your recovery key is ' + client_info['recovery_key'])
    else:
        # The client has a username and they are not yet registered, so begin the recovery process
        if len(update.message.text.split(' ')) == 1:
            # If the user has only entered /recover, notify them of the correct formatting:
            bot.send_message(chat_id=update.message.chat_id, text='Please use /recover <recovery key> to recover access to your funds.')
        elif len(update.message.text.split(' ')) != 2:
            # If the client entered more than a single word for the key, throw an error
            bot.send_message(chat_id=update.message.chat_id, text='Invalid recovery key. Please try again.')
        else:
            # Get client info corresponding to recovery key
            localdb = dataset.connect('sqlite:///' + settings.local_db_name)
            users_table = localdb['users']
            recoverykey = update.message.text.split(' ')[1]
            client_info_current = users_table.find_one(recovery_key=recoverykey)
            if not client_info_current:
                # Recovery key did not match any keys in record
                bot.send_message(chat_id=update.message.chat_id, text='Invalid recovery key. Please try again.')
            else:
                # Recovery key corresponded to an entry in the database
                # Update username of the entry to the client's username
                users_table.update(dict(user_id=client_username, recovery_key=recoverykey), ['recovery_key'])
                client_info_new = users_table.find_one(user_id=client_username)
                logger.info('Updated user_id for address ' + client_info_current['xrb_address'] + ' from ' + client_info_current['user_id'] + ' to ' + client_info_new['user_id'])
                # Display the update success to the client:
                bot.send_message(chat_id=update.message.chat_id, text='Recovery successful! \n\n' +
                                                                      'Old username ' + client_info_current['user_id'] + '\n'
                                                                      'New username ' + client_info_new['user_id'] + '\n\n'
                                                                      'Please use /balance to check your balance.')


def tip(bot, update):
    # Attempt to fetch the username of the client
    client_username = str(update.message.from_user.username)
    if client_username == 'None':
        # If the username is 'None', the client has not set a username and thus cannot register
        send_username_error(bot, update)
    else:
        client_info = check_username(client_username)

        if not client_info:
            # If the user does not exist in the database they must register before checking their balance
            bot.send_message(chat_id=update.message.chat_id, text='You have not yet been registered for the Nano Tipbot.\n\n'
                                                                  'Please use /register to sign up.')
        else:
            # Check to ensure that the tip command has the correct format - "/tip username amount"
            # If the user has only entered /tip, notify them of the correct formatting:
            if len(update.message.text.split(' ')) == 1:
                bot.send_message(chat_id=update.message.chat_id, text='Please use /tip <username> <amount> to tip a user.\n\n'
                                                                      'Example:\n'
                                                                      '/tip nano_tipbot 0.001')
            elif len(update.message.text.split(' ')) != 3:
                bot.send_message(chat_id=update.message.chat_id, text='Incorrect format. \n\n'
                                                                      'Please use /tip <username> <amount> \n\n'
                                                                      'Example:\n'
                                                                      '/tip nano_tipbot 0.001')
            else:
                # Check to see if the recipient is registered with the tip bot.
                recipient_username = update.message.text.split(' ')[1]
                if recipient_username == client_username:
                    # If the recipient username is the same as the client username throw an error
                    bot.send_message(chat_id=update.message.chat_id, text='You can\'t tip yourself!')
                else:
                    # Get the amount to send:
                    send_amount = update.message.text.split(' ')[2]

                    recipient_info = check_username(recipient_username)

                    if not recipient_info:
                        # Flag this recipient as a new recipient
                        new_recipient = True
                        # Create an account for the new recipient
                        localdb = dataset.connect('sqlite:///' + settings.local_db_name)
                        users_table = localdb['users']
                        # Create account
                        wallet_command = {'action': 'account_create', 'wallet': wallet}
                        wallet_output = communicate_wallet(wallet_command)
                        address = wallet_output['account']
                        # Create recovery key (UUID4 token)
                        recoverykey = str(uuid.uuid4())
                        # Insert row containing username, account and recovery key into database
                        logger.info('Registered user ' + recipient_username + ' with address ' + address + ' and recovery key ' + recoverykey)
                        users_table.insert(dict(user_id=recipient_username, xrb_address=str(address), recovery_key=recoverykey))
                        # Refresh the recipient_info
                        recipient_info = check_username(recipient_username)

                    else:
                        new_recipient = False

                    try:
                        # Get the address of the client and recipient
                        client_address = client_info['xrb_address']
                        recipient_address = recipient_info['xrb_address']

                        # Get the balance of the client to ensure that they have enough Nano in their account
                        wallet_command = {'action': 'account_balance', 'account': client_address}
                        wallet_output = communicate_wallet(wallet_command)

                        wallet_command = {'action': 'rai_from_raw', 'amount': int(wallet_output['balance'])}
                        client_balance = communicate_wallet(wallet_command)

                        rai_send_amount = float(send_amount) * 1000000
                        raw_send_amount = str(int(rai_send_amount)) + '000000000000000000000000'

                        if int(rai_send_amount) <= int(client_balance['amount']):
                            wallet_command = {'action': 'send', 'wallet': wallet, 'source': client_address, 'destination': recipient_address, 'amount': int(raw_send_amount)}
                            wallet_output = communicate_wallet(wallet_command)
                            logger.info('User ' + client_username + ' (address ' + client_address + ') sent user ' + recipient_username + ' (address ' + recipient_address + ') Nano ' + send_amount)
                            bot.send_message(chat_id=update.message.chat_id, text='You have successfully tipped @' + recipient_username + ' with Nano ' + send_amount + '\n\n'
                                                                                  'Thank you for using the Nano Tipbot! \n\n'
                                                                                  'Let @' + recipient_username + ' know that you have tipped them by sending them the message below.')
                            if new_recipient:
                                bot.send_message(chat_id=update.message.chat_id, text='@' + recipient_username + ' has been tipped Nano ' + send_amount + ' using the Nano Tipbot (@nano_tipbot) courtesy of @' + client_username + '.\n\n' +
                                                                                      '@' + recipient_username + ', an account has been created for you on @nano_tipbot where you can access your funds.')
                            else:
                                bot.send_message(chat_id=update.message.chat_id, text='@' + recipient_username + ' has been tipped Nano ' + send_amount + ' using the Nano Tipbot (@nano_tipbot) courtesy of @' + client_username + '.')
                        else:
                            bot.send_message(chat_id=update.message.chat_id, text='Not enough funds to send Nano ' + send_amount + '\n\n'
                                                                                  'Please use /balance to check your account balance.')
                    except:
                        bot.send_message(chat_id=update.message.chat_id, text='Invalid amount entered: ' + send_amount)


def withdraw(bot, update):
    # Attempt to fetch the username of the client
    client_username = str(update.message.from_user.username)
    if client_username == 'None':
        # If the username is 'None', the client has not set a username and thus cannot register
        send_username_error(bot, update)
    else:
        client_info = check_username(client_username)

        if not client_info:
            # If the user does not exist in the database they must register before checking their balance
            bot.send_message(chat_id=update.message.chat_id, text='You have not yet been registered for the Nano Tipbot.\n\n'
                                                                  'Please use /register to sign up.')
        else:
            # If the user has only entered /withdraw, notify them of the correct formatting:
            if len(update.message.text.split(' ')) == 1:
                bot.send_message(chat_id=update.message.chat_id, text='Please use /withdraw <address> <amount> to withdraw your funds.')
            # Check to ensure that the withdraw command has the correct format - "/withdraw address amount"
            elif len(update.message.text.split(' ')) != 3:
                bot.send_message(chat_id=update.message.chat_id, text='Incorrect format. \n\n'
                                                                      'Please use /withdraw <address> <amount>')
            else:
                # Check to see if the withdraw address is valid
                withdraw_address = update.message.text.split(' ')[1]
                wallet_command = {"action": "validate_account_number", "account": withdraw_address}
                address_validation = communicate_wallet(wallet_command)
                # If the address was the incorrect length, did not start with xrb_ or nano_ or was deemed invalid by the node, return an error.
                address_prefix_valid = withdraw_address[:4] == "xrb_" or withdraw_address[:5] == "nano_"
                if len(withdraw_address) != 64 or not address_prefix_valid or address_validation['valid'] != '1':
                    bot.send_message(chat_id=update.message.chat_id, text='The address: ' +
                                                                          withdraw_address + ' '
                                                                          'is not a valid address. \n\n'
                                                                          'Please check the address and try again.')
                else:
                    try:
                        # Get the address of the client
                        client_address = client_info['xrb_address']

                        # Get the amount to send:
                        withdraw_amount = update.message.text.split(' ')[2]

                        # Get the balance of the client to ensure that they have enough Nano in their account
                        wallet_command = {'action': 'account_balance', 'account': client_address}
                        wallet_output = communicate_wallet(wallet_command)

                        wallet_command = {'action': 'rai_from_raw', 'amount': int(wallet_output['balance'])}
                        client_balance = communicate_wallet(wallet_command)

                        rai_withdraw_amount = float(withdraw_amount) * 1000000
                        raw_withdraw_amount = str(int(rai_withdraw_amount)) + '000000000000000000000000'

                        if int(rai_withdraw_amount) <= int(client_balance['amount']):
                            wallet_command = {'action': 'send', 'wallet': wallet, 'source': client_address, 'destination': withdraw_address, 'amount': int(raw_withdraw_amount)}
                            wallet_output = communicate_wallet(wallet_command)
                            logger.info('User ' + client_username + ' (address ' + client_address + ') withdrew Nano ' + withdraw_amount + ' to address ' + withdraw_address)
                            bot.send_message(chat_id=update.message.chat_id, text='You have successfully withdrawn Nano ' + withdraw_amount + ' to ' + withdraw_address + '\n\n'
                                                                                  'Thank you for using the Nano Tipbot!')
                        else:
                            bot.send_message(chat_id=update.message.chat_id, text='Not enough funds to withdraw Nano ' + withdraw_amount + '\n\n'
                                                                                  'Please use /balance to check your account balance.')
                    except:
                        bot.send_message(chat_id=update.message.chat_id, text='Invalid amount entered: ' + withdraw_amount)


def contribute(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text='Thanks for your interest in contributing!\n\n'
                                                          'This project is run as a labour of love, but if you would like to help '
                                                          'cover my almost nonexistent server costs or buy me a coffee feel free to tip the bot:\n\n'
                                                          '/tip nano_tipbot <amount> \n\n'
                                                          'or contribute directly to:\n\n'
                                                          'xrb_1meyyw7s1kia5e368e8oyb4coydqfb6gkoroxgeofjyedohhs1g5dak8en75 \n\n'
                                                          'Thanks for using the Nano Tipbot!')


def update_price_info(bot, job):
    global PriceInfo
    nano_market_data = requests.get('https://api.coinmarketcap.com/v1/ticker/raiblocks/')
    PriceInfo = nano_market_data.json()


start_handler = CommandHandler('start', start)
help_handler = CommandHandler('help', help)
price_handler = CommandHandler('price', price)
register_handler = CommandHandler('register', register)
balance_handler = CommandHandler('balance', balance)
deposit_handler = CommandHandler('deposit', balance)
recover_handler = CommandHandler('recover', recover)
tip_handler = CommandHandler('tip', tip)
withdraw_handler = CommandHandler('withdraw', withdraw)
contribute_handler = CommandHandler('contribute', contribute)

dispatcher.add_handler(start_handler)
dispatcher.add_handler(help_handler)
dispatcher.add_handler(price_handler)
dispatcher.add_handler(register_handler)
dispatcher.add_handler(balance_handler)
dispatcher.add_handler(deposit_handler)
dispatcher.add_handler(recover_handler)
dispatcher.add_handler(tip_handler)
dispatcher.add_handler(withdraw_handler)
dispatcher.add_handler(contribute_handler)

# Start running a job that refreshes the price information once every 5 minutes
refresh_price_job = jobqueue.run_repeating(update_price_info, interval=300, first=0)

updater.start_polling()

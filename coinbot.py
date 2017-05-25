#!/usr/bin/python3
import sys
import json
import smtplib
import hmac, hashlib, time, base64
import requests
from requests.auth import AuthBase
from decimal import Decimal, ROUND_DOWN

API_URL = 'https://api.gdax.com/'

#ANSI Colors
colors = {
	'black':	"\x1b[30m",
	'red':		"\x1b[31m",
	'green':	"\x1b[32m",
	'yellow':	"\x1b[33m",
	'blue':		"\x1b[34m",
	'magenta':	"\x1b[35m",
	'cyan':		"\x1b[36m",
	'white':	"\x1b[37m",
	'reset':	"\x1b[0m"
}

# Global auth object
auth = {}

# JSON serializer for Decimal
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError

# Custom authentication for GDAX
class GDAXAuth(AuthBase):
	def __init__(self, api_key, secret_key, passphrase):
		self.api_key = api_key
		self.secret_key = secret_key
		self.passphrase = passphrase

	def __call__(self, request):
		timestamp = str(time.time())
		message = timestamp + request.method + request.path_url + (request.body or '')
		hmac_key = base64.b64decode(self.secret_key)
		signature = hmac.new(hmac_key, message.encode('ascii'), hashlib.sha256)
		signature_b64 = base64.b64encode(signature.digest())

		request.headers.update({
			'CB-ACCESS-SIGN': signature_b64,
			'CB-ACCESS-TIMESTAMP': timestamp,
			'CB-ACCESS-KEY': self.api_key,
			'CB-ACCESS-PASSPHRASE': self.passphrase,
			'Content-Type': 'application/json'
		})
		return request

# API call wrapper function
def api(endpoint, params=None, delete=False, notFoundOK=False, isAbort=False):
	if(params != None):
		r = requests.post(API_URL + endpoint, auth=auth, data=json.dumps(params, default=decimal_default), headers={"Content-Type": "text/javascript"})
	elif(delete):
		r = requests.delete(API_URL + endpoint, auth=auth)
	else:
		r = requests.get(API_URL + endpoint, auth=auth)
	if(r.status_code == 200 or (notFoundOK and r.status_code == 404)):
		return r.json()
	else:
		message = 'Error getting data from API: ' + endpoint + '\n'
		try:
			message += 'Response: ' + r.json()['message'] + '\n'
		except(ValueError):
			pass
		message += 'Params: ' + (json.dumps(params, default=decimal_default, indent=4) if params != None else 'None') + '\n'
		message += 'Raw: ' + r.text + '\n'
		log(message)
		if(isAbort == False):
			#abort()
			return None
		else:
			sys.exit(1)

# Write state to file
def savestate(state):
	statefile = open('state', 'w')
	statefile.seek(0)
	statefile.write(json.dumps(state, default=decimal_default, indent=4))
	statefile.close()

# Send email on trade
def log(message):
	print(message)
	statefile = open('log', 'a')
	statefile.write(message)
	statefile.close()
	#message = 'From: coinbot\nSubject: CoinBot Notification\n' + message
	#smtp = smtplib.SMTP('localhost')
	#smtp.sendmail('coinbot', 'dare', message)
	#smtp.quit()

# Cancel everything and exit
def abort():
	api('orders', delete=True, isAbort=True)
	sys.exit(1)


# Place an order
def placeOrder(state, side, amount, price):
	order = {
#		'price': price,
		'type': 'market',
		'product_id': 'BTC-USD'
#		'post_only': True
	}
	if(side == 'buy'):
		order['funds'] = amount
		order['side'] = 'buy'
		log('Placing buy order for {:.8f} BTC at ${:.2f}/coin (total ${:.2f})'.format(amount/price, price, amount))
		state['buyOrder'] = order
	else:
		order['size'] = amount
		order['side'] = 'sell'
		log('Placing sell order for {:.8f} BTC at ${:.2f}/coin (total ${:.2f})'.format(amount, price, amount*price))
		state['sellOrder'] = order
	return api('orders', order)

# Cancel an order
def cancelOrder(state, side):
	result = {}
	if(side == 'buy' and state['buyOrder'] != None):
		log('Cancelling buy order for {:.8f} BTC at ${:.2f}/coin (total ${:.2f})'.format(
			Decimal(state['buyOrder']['funds'])/Decimal(state['buyOrder']['price']),
			Decimal(state['buyOrder']['price']),
			Decimal(state['buyOrder']['funds'])
		))
		result = api('orders/' + state['buyOrder']['id'], delete=True, notFoundOK=True)
		state['buyOrder'] = None
	elif(side == 'sell' and state['sellOrder'] != None):
		log('Cancelling sell order for {:.8f} BTC at ${:.2f}/coin (total ${:.2f})'.format(
			Decimal(state['sellOrder']['size']),
			Decimal(state['sellOrder']['price']),
			Decimal(state['sellOrder']['size'])*Decimal(state['sellOrder']['price'])
		))
		result = api('orders/' + state['sellOrder']['id'], delete=True, notFoundOK=True)
		state['sellOrder'] = None
	return result

# Check if an order has completed
def checkOrderComplete(state, orderID, price, costBasis):
	order = api('orders/' + orderID, notFoundOK=True)
	if(order == None or ('message' in order and order['message'] == 'NotFound')):
		return False

	#Order completed
	if(order['status'] == 'done' or order['status'] == 'settled'):
		#Sell order
		if(order['side'] == 'sell'):
			state['lastSell'] = Decimal(order['executed_value'])
			state['min'] = state['currentPrice']
			log('Sold {:.8f} BTC at price ${:.2f}. Profit: ${:.2f}'.format(
				Decimal(order['filled_size']),
				price,
				(price - costBasis) * Decimal(order['filled_size'])
			))
			state['sellOrder'] = None
		#Buy order
		elif(order['side'] == 'buy'):
			state['lastSell'] = Decimal(0.0)
			state['costBasis'] = price*Decimal(1.0025)
			state['max'] = state['currentPrice']
			log('Bought {:.8f} BTC at price ${:.2f}'.format(
				Decimal(order['filled_size']),
				price
			))
			state['buyOrder'] = None
		return False

	#Order not placed
	elif(order['status'] == 'rejected'):
		log('Order ' + order['id'] + ' rejected, continuing...')
		if(order['side'] == 'sell'):
			state['sellOrder'] = None
		else:
			state['buyOrder'] = None

	#Error with order
	elif(order['status'] != 'pending' and order['status'] != 'open'):
		log('Error processing order ' + order['id'] + '(' + order['status'] + '), exiting...')
		abort()

	#Otherwise, order pending
	return True


# Business logic
# Manual hold until 5% increase from basis
# Sell after 2% drop from max-since-buy, or drop below basis
# Buy after increase from last sell, or 2.5% increase from min-since-sell while below basis
def logic(state):
	# Set targets
	costBasis = state['costBasis']
	holdUntil = costBasis * Decimal(1.05)
	balanceUSD = state['balanceUSD'].quantize(Decimal('.01'), rounding=ROUND_DOWN)
	balanceBTC = state['balanceBTC'].quantize(Decimal('.01'), rounding=ROUND_DOWN)

	current = state['currentPrice'].quantize(Decimal('.01'), rounding=ROUND_DOWN)
	sellTarget = (state['max'] * Decimal(0.98)).quantize(Decimal('.01'), rounding=ROUND_DOWN)
	sellStop = costBasis.quantize(Decimal('.01'), rounding=ROUND_DOWN) * Decimal(0.99)
	buyTarget = (state['min'] * Decimal(1.025)).quantize(Decimal('.01'), rounding=ROUND_DOWN)
	buyStop = state['lastSell'].quantize(Decimal('.01'), rounding=ROUND_DOWN) * Decimal(1.01)

	print('BTC price: {}{:.2f}{} Value: {}{:.2f}{}'.format(colors['cyan'], current, colors['reset'], colors['cyan'], ((balanceBTC*current)+balanceUSD), colors['reset']), end='')
	print(' (sell at {}{:.2f}{}|{}{:.2f}{},'.format(colors['green'], sellTarget, colors['reset'], colors['green'], sellStop, colors['reset']), end='')
	print(' buy at {}{:.2f}{}|{}{:.2f}{})'.format(colors['red'], buyTarget if buyTarget < costBasis else 0, colors['reset'], colors['red'], buyStop, colors['reset']), end='')
	if(state['hold']):
		print(' {}[HOLDING UNTIL {:.2f}]{}'.format(colors['yellow'], holdUntil, colors['reset']))
	else:
		print('')

	# Check order state
	if(state['sellOrder'] != None):
		if(checkOrderComplete(state, state['sellOrder']['id'], current, costBasis) == False):
			state['sellOrder'] = None
	if(state['buyOrder'] != None):
		if(checkOrderComplete(state, state['buyOrder']['id'], current, costBasis) == False):
			state['buyOrder'] = None

	if(state['hold'] and current >= holdUntil):
		state['hold'] = False
	elif(state['hold']):
		return

	# Sell coins
	if(state['sellEnabled'] and balanceBTC > 0.0 and (current < sellStop or current <= sellTarget)):
		if(state['sellOrder'] == None):
			state['sellOrder'] = placeOrder(state, 'sell', balanceBTC, current)
#		elif(Decimal(state['sellOrder']['price']) != current):
#			cancelOrder(state, 'sell')
#			state['sellOrder'] = placeOrder(state, 'sell', balanceBTC, current)
	elif(state['sellOrder'] != None):
		cancelOrder(state, 'sell')

	# Buy coins
	if(state['buyEnabled'] and balanceUSD > 0.0 and state['lastSell'] != Decimal(0.0) and (current > buyStop or (buyTarget < costBasis and current >= buyTarget))):
		if(state['buyOrder'] == None):
			state['buyOrder'] = placeOrder(state, 'buy', balanceUSD, current)
#		elif(Decimal(state['buyOrder']['price']) != current):
#			cancelOrder(state, 'buy')
#			state['buyOrder'] = placeOrder(state, 'buy', balanceUSD, current)
	elif(state['buyOrder'] != None):
		cancelOrder(state, 'buy')

# Program entry point
def main(argv):
	global auth
	authfile = open('auth.json', 'r')
	authdata = json.load(authfile)
	authfile.close()
	auth = GDAXAuth(authdata['API_KEY'], authdata['API_SECRET'], authdata['API_PASS'])
	print('Coinbot initialized.')

	# Load previous state, or start afresh
	state = {}
	try:
		file = open('state', 'r')
		state = json.load(file)
		state['costBasis'] = Decimal(state['costBasis'])
		state['max'] = Decimal(state['max'])
		state['min'] = Decimal(state['min'])
		state['balanceBTC'] = Decimal(state['balanceBTC'])
		state['balanceUSD'] = Decimal(state['balanceUSD'])
		state['lastSell'] = Decimal(state['lastSell'])
		file.close()
	except(FileNotFoundError, ValueError):
		state['costBasis'] = Decimal(api('products/BTC-USD/ticker')['price'])
		state['max'] = state['costBasis']
		state['min'] = state['costBasis']
		state['lastSell'] = Decimal(0.0)
		state['sellOrder'] = None
		state['buyOrder'] = None
		state['hold'] = True

	# Get accounts
	accounts = api('accounts');
	for account in accounts:
		if(account['currency'] == 'BTC' or account['currency'] == 'USD'):
			print('{}: {}{:.8f}{}'.format(account['currency'], colors['magenta'], Decimal(account['balance']), colors['reset']))
			state['balance' + account['currency']] = Decimal(account['balance'])

	state['buyEnabled'] = True
	state['sellEnabled'] = True

	savestate(state)

	#Rules
	print('Rules:')
	print('Manual hold until 5% increase from basis')
	print('Sell after 2% drop from max-since-buy, or drop below basis')
	print('Buy after increase from last sell, or 2.5% increase from min-since-sell while below basis')
	print('Buys: {}{}{}'.format(colors['green'] if state['buyEnabled'] else colors['red'], 'ENABLED' if state['buyEnabled'] else 'DISABLED', colors['reset']))
	print('Sells: {}{}{}'.format(colors['green'] if state['sellEnabled'] else colors['red'], 'ENABLED' if state['sellEnabled'] else 'DISABLED', colors['reset']))

	# Main program loop
	while(True):
		tick = api('products/BTC-USD/ticker')
		accounts = api('accounts')
		for account in accounts:
			if(account['currency'] == 'BTC' or account['currency'] == 'USD'):
				state['balance' + account['currency']] = Decimal(account['balance'])

		state['currentPrice'] = (Decimal(tick['bid'])+Decimal(tick['ask']))/Decimal(2)
		if(state['currentPrice'] > state['max']):
			state['max'] = state['currentPrice']
		elif(state['currentPrice'] < state['min']):
			state['min'] = state['currentPrice']

		logic(state)

		savestate(state)
		time.sleep(1)

if(__name__ == '__main__'):
	try:
		main(sys.argv)
	except KeyboardInterrupt:
		sys.exit(0)

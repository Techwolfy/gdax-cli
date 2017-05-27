#!/usr/bin/python3
import sys
import json
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
	'reset':	"\x1b[0m",
	'clear':	"\x1b[2J"
}

# Global auth object
auth = None

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
def api(endpoint, params=None, delete=False, notFoundOK=False):
	if(params != None):
		r = requests.post(API_URL + endpoint, auth=auth, data=json.dumps(params, default=decimal_default), headers={"Content-Type": "text/javascript"})
	elif(delete):
		r = requests.delete(API_URL + endpoint, auth=auth)
	else:
		r = requests.get(API_URL + endpoint, auth=auth)
	if(r.status_code == 200 or (notFoundOK and r.status_code == 404)):
		if(r.text == ''):
			return {}
		else:
			return r.json()
	else:
		message = 'Error getting data from API: ' + endpoint + '\n'
		try:
			message += 'Response: ' + r.json()['message'] + '\n'
		except(ValueError):
			pass
		message += 'Params: ' + (json.dumps(params, default=decimal_default, indent=4) if params != None else 'None') + '\n'
		message += 'Raw: ' + r.text + '\n'
		print(message)
		return None

# Get current market ticker
def getTicker(silent=True):
	tick = api('products/BTC-USD/ticker')
	if(not silent):
		print('Market price: {:.2f}'.format(Decimal(tick['price'])))
	return tick

# Watch the market ticker
def watchTicker():
	last = Decimal(0.0)
	while(True):
		tick = Decimal(getTicker()['price'])

		if(tick > last):
			print('Market price: {}{:.2f}{}'.format(colors['green'], tick, colors['reset']))
		elif(tick < last):
			print('Market price: {}{:.2f}{}'.format(colors['red'], tick, colors['reset']))
		else:
			print('Market price: {:.2f}'.format(tick))

		last = tick
	return

# Get the full order book
def getOrderBook(silent=True, clear=False):
	book = api('products/BTC-USD/book?level=2')
	if(silent):
		return book

	if(clear):
		print(colors['clear'])

	spreadstr = 'Spread: {}${:.2f}{}'.format(
		colors['yellow'],
		Decimal(book['asks'][0][0]) - Decimal(book['bids'][0][0]),
		colors['reset']
	)
	mmpstr = 'Mid-Market Price: {}${:.2f}{}'.format(
		colors['yellow'],
		(Decimal(book['asks'][0][0]) + Decimal(book['bids'][0][0])) / 2,
		colors['reset']
	)
	padding = 40 - len(spreadstr)
	print(spreadstr + (' ' * padding) + mmpstr)
	print('')

	bidtotal = Decimal(0.0)
	asktotal = Decimal(0.0)
	for i in range (0, 24):
		bidtotal += Decimal(book['bids'][i][1])
		asktotal += Decimal(book['asks'][i][1])

	print((' ' * 8) + 'Bid' + (' ' * 28) + 'Ask')
	for i in range(0, 24):
		bidstr = '{}${:.2f}{}: {:.8f} {}'.format(
			colors['green'],
			Decimal(book['bids'][i][0]),
			colors['reset'],
			Decimal(book['bids'][i][1]),
			'\u2588' * min(int(32 * Decimal(book['bids'][i][1]) / bidtotal), 8)
		)
		askstr = '{}${:.2f}{}: {:.8f} {}'.format(
			colors['red'],
			Decimal(book['asks'][i][0]),
			colors['reset'],
			Decimal(book['asks'][i][1]),
			'\u2588' * min(int(32 * Decimal(book['asks'][i][1]) / asktotal), 8)
		)
		padding = 40 - len(bidstr)
		print(bidstr + (' ' * padding) + askstr)

	bidtotalstr = 'Total:    {:.8f}'.format(bidtotal)
	asktotalstr = 'Total:    {:.8f}'.format(asktotal)
	padding = 27 - len(bidtotalstr)
	dirstr = '>>>>' if bidtotal > asktotal else '<<<<'
	print(bidtotalstr + (' ' * int(padding/2)) + dirstr + (' ' * int(padding - padding/2)) + asktotalstr)

	return book

# Watch live order book updates
def watchOrderBook():
	while(True):
		getOrderBook(silent=False, clear=True)
		time.sleep(1)
	return

# Get account balances
def getAccounts(silent=True):
	out = {};
	accounts = api('accounts');
	for account in accounts:
		if(account['currency'] == 'BTC' or account['currency'] == 'USD'):
			if(not silent):
				print('{}: {:.8f}'.format(account['currency'], Decimal(account['balance'])))
			out[account['currency']] = Decimal(account['balance'])
	return out

# Get all current orders
def getOrderList(silent=True):
	orders = api('orders?status=open')
	if(not silent):
		for i, order in enumerate(orders):
			print('{}: {} ({}): {} {} {:.8f}BTC at ${:.2f}'.format(
				i,
				order['id'],
				order['status'],
				order['type'],
				order['side'],
				Decimal(order['size']),
				Decimal(order['price'])
			))
	return orders

# Get an order and check if it order has completed
def getOrder(oid, silent=True):
	order = api('orders/' + oid, notFoundOK=True)
	if(order == None or ('message' in order and order['message'] == 'NotFound')):
		if(not silent):
			print('Order not found')
		return None

	#Order completed
	if(not silent and (order['status'] == 'done' or order['status'] == 'settled')):
		verb = 'Sold' if order['side'] == 'sell' else 'Bought'
		print(verb + '{:.8f} BTC at ${:.2f}'.format(Decimal(order['filled_size']), order['funds']))

	#Order not placed
	elif(not silent and order['status'] == 'rejected'):
		print('Order was rejected')

	#Error with order
	elif(not silent and order['status'] != 'open' and order['status'] != 'pending'):
		print('Error processing order (status: ' + order['status'] + ')')

	#Order pending
	elif(not silent):
		print('{} {} {:.8f}BTC at ${:.2f} (pending)'.format(
				order['type'],
				order['side'],
				Decimal(order['size']),
				Decimal(order['price'])
			))

	return order

# Place an order
def placeOrder(otype, side, size, price, silent=False):
	order = {
		'product_id': 'BTC-USD',
		'type': otype,
		'side': side,
		'size': '{:.8f}'.format(Decimal(size)),
		'price': '{:.8f}'.format(Decimal(price)),
		'post_only': False if otype == 'market' else True
	}

	if(not silent):
		action = input('Place {} {} order for {:.8f} BTC at ${:.2f}/coin (y/N)? '.format(
			order['type'],
			order['side'],
			Decimal(order['size']),
			Decimal(order['price'])
		))

	if(action.lower() == 'y' or silent):
		result = api('orders', order)
	else:
		result = None

	if(not silent):
		if(result == None):
			print('Failed to place order!')
		else:
			print('Order placed successfully (ID ' + result['id'] + ')')

	return result

# Cancel an order
def cancelOrder(oid, silent=True):
	order = getOrder(oid)
	if(order == None):
		if(not silent):
			print('Order does not exist')
		return None

	result = api('orders/' + oid, delete=True, notFoundOK=True)
	if(not silent):
		if(result == {} or result[0] == oid):
			print('Cancelled {} {} order for {:.8f} BTC at ${:.2f}/coin'.format(
				order['type'],
				order['side'],
				Decimal(order['size']),
				Decimal(order['price'])
			))
		else:
			print('Failed to cancel order!')

	return result

# Watch the status of an order
def watchOrder(oid, silent=True):
	order = getOrder(oid, silent)
	while(order != None and (order['status'] == 'open' or order['status'] == 'pending')):
		time.sleep(1)
		order = getOrder(oid, silent)
	return

# Program entry point
def main(argv):
	global auth
	authfile = open('auth.json', 'r')
	authdata = json.load(authfile)
	authfile.close()
	auth = GDAXAuth(authdata['API_KEY'], authdata['API_SECRET'], authdata['API_PASS'])

	if(len(argv) == 3 and len(argv[2]) <= 2):
		oid = getOrderList()[int(argv[2])]['id']
		argv[2] = oid

	# Main program loop
	if(len(argv) < 2):
		help()
	elif(argv[1] == 'ticker'):
		getTicker(silent=False)
	elif(argv[1] == 'orderbook'):
		getOrderBook(silent=False)
	elif(argv[1] == 'balance'):
		getAccounts(silent=False)
	elif(argv[1] == 'orders'):
		getOrderList(silent=False)
	elif(argv[1] == 'order' and len(argv) == 3):
		getOrder(argv[2], silent=False)
	elif(argv[1] == 'watch' and len(argv) == 3):
		watchOrder(argv[2], silent=False)
	elif(argv[1] == 'buy' or argv[1] == 'sell' and len(argv) == 4):
		placeOrder('market', argv[1], argv[2], argv[3], silent=False)
	elif((argv[1] == 'market' or argv[1] == 'limit' or argv[1] == 'stop') and len(argv) == 5):
		placeOrder(argv[1], argv[2], argv[3], argv[4], silent=False)
	elif(argv[1] == 'cancel' and len(argv) == 3):
		cancelOrder(argv[2], silent=False)
	elif(argv[1] == 'live'):
		watchOrderBook()
	elif(argv[1] == 'liveticker'):
		watchTicker()
	else:
		help()
	return

# Print usage instructions
def help():
	print("Usage: gdax <command> [arguments]")
	print("    ticker                                           Get current market ticker")
	print("    orderbook                                        Get current order book data")
	print("    balance                                          Get current account balance")
	print("    orders                                           Get list of existing orders")
	print("    order [order ID]                                 Get details of existing order")
	print("    watch [order ID]                                 Watch order for completion")
	print("    buy/sell [BTC amount]                            Market buy/sell BTC")
	print("    market buy/sell [BTC amount]                     Alias for buy/sell")
	print("    limit buy/sell [BTC amount] [limit price]        Limit buy/sell BTC")
	print("    stop buy/sell [BTC amount] [stop price]          Stop buy/sell BTC")
	print("    live                                             Live stream of order book data")
	print("    liveticker                                       Live stream of ticker data")
	return

#Shell entry point
if(__name__ == '__main__'):
	try:
		main(sys.argv)
	except KeyboardInterrupt:
		sys.exit(0)

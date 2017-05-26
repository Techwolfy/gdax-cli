GDAX-CLI
========

A command-line interface for GDAX (Global Digital Asset Exchange). The standard web interface is incapable of handling the load during major market shifts, but the trading engine does not pause during this time. This client allows trading to continue as long as the backend API remains accessible.


Usage
-----

Create an API key on GDAX with "read" and "trade" permissions, then update the relevant variables in [`auth.json`](auth.json).

```
Usage: gdax <command> [arguments]
    ticker                                           Get current market ticker
    balance                                          Get current account balance
    orders                                           Get list of existing orders
    order [order ID]                                 Get details of existing order
    watch [order ID]                                 Watch order for completion
    buy/sell [BTC amount]                            Market buy/sell BTC
    market buy/sell [BTC amount]                     Alias for buy/sell
    limit buy/sell [BTC amount] [limit price]        Limit buy/sell BTC
    stop buy/sell [BTC amount] [stop price]          Stop buy/sell BTC
    live                                             Live stream of ticker data
    orderbook                                        Live stream of order book
```


Dependencies
------------

- python3
- python3-requests


License
-------

GDAX-CLI is released under the GNU General Public License, version 3.0. For more informaion, please see [`COPYING`](COPYING).

DISCLAIMER: No warranty is provided for this software. Use it at your own risk.

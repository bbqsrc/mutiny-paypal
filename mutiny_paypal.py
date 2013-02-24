import yaml
import json
import requests
import logging
import time

from collections import OrderedDict

class PayPalAPI:
    def __init__(self, config):
        self.config = config

    def paypal_request(self, method, data):
        url = self.config['endpoint'].rstrip("/") + "/" + method
        headers = OrderedDict([
            ("X-PAYPAL-SECURITY-USERID", self.config['username']),
            ("X-PAYPAL-SECURITY-PASSWORD", self.config['password']),
            ("X-PAYPAL-SECURITY-SIGNATURE", self.config['signature']),
            ("X-PAYPAL-APPLICATION-ID", self.config['app_id']),
            ("X-PAYPAL-REQUEST-DATA-FORMAT", "JSON"),
            ("X-PAYPAL-RESPONSE-DATA-FORMAT", "JSON"),
            ("Content-Type", "application/json")
        ])

        for attempt in range(3):
            r = requests.post(url, data=json.dumps(data), headers=headers)
            res = json.loads(r.text)
            response_envelope = res['responseEnvelope']
            logging.debug(res)
            if response_envelope['ack'].startswith("Failure") and\
                    res['error'][0]['errorId'] == "520002":
                wait_t = 0.5 * pow(2, attempt) # exponential back off
                time.sleep(wait_t)
            else:
                break

        return res


    def get_merchant_info(self):
        return OrderedDict([
            ('businessName', self.config['merchant_info']['business_name']),
            ('website', self.config['merchant_info']['website'])
        ])


    def create_and_send_invoice(self, merchant_email, payer_email, merchant_info, biller_info, items, payment_terms="DueOnReceipt", currency_code="AUD"):
        if isinstance(items, dict):
            items = [items]

        data = {"invoice": OrderedDict([
            ("payerEmail", payer_email),
            ("merchantEmail", merchant_email),
            ("currencyCode", currency_code),
            ("paymentTerms", payment_terms),
            ("merchantInfo", merchant_info),
            ("billingInfo", biller_info),
            ("itemList", {"item": items}),
            ("requestEnvelope", {"errorLanguage": "en_US"})
        ])}
        return self.paypal_request("Invoice/CreateAndSendInvoice", data)

    @classmethod
    def create_biller_info(cls, first_name, last_name, phone, address1, address2, suburb, state, postcode, country="AU"):
        address = OrderedDict()
        address['line1'] = address1
        if address2 is not None:
            address['line2'] = address2
        address['city'] = suburb
        address['state'] = state
        address['postalCode'] = postcode
        address['countryCode'] = country

        return OrderedDict([
            ("firstName", first_name),
            ("lastName", last_name),
            ("phone", phone),
            ("address", address)
        ])

    @classmethod
    def create_invoice_item(cls, name, price, quantity="1", desc=None, tax_name=None, tax_rate=None):
        x = OrderedDict([
            ("name", name),
            ("quantity", str(quantity)),
            ("unitPrice", str(price))
        ])
        if desc is not None:
            x['description'] = desc
        if tax_name is not None:
            x['taxName'] = tax_name
        if tax_rate is not None:
            x['taxRate'] = str(tax_rate)
        return x

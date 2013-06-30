import yaml
import json
import requests
import logging
import time
import re

from collections import OrderedDict
from urllib.parse import quote, unquote

class PayPalAPI:
    @classmethod
    def dict_to_nvp(cls, dct):
        out = []
        for key, value in dct.items():
            if isinstance(value, dict):
                for n, k in enumerate(value):
                    out.append("%s%s=%s%%3D%s" % (key, n, k, quote(str(value[k]))))
            elif isinstance(value, list):
                for n, item in enumerate(value):
                    out.append("%s%s=%s" % (key, n+1, quote(str(item))))
            else:
                out.append("%s=%s" % (key, quote(str(value))))
        return "&".join(out)

    @classmethod
    def nvp_to_dict(cls, nvp):
        end_numbers = re.compile(r"(.+?)(\d+)$")
        out = OrderedDict()
        splits = OrderedDict([x.split('=') for x in nvp.split("&")])

        for key, value in splits.items():
            value = unquote(value)
            result = end_numbers.search(key)
            if result is not None:
                if out.get(result.group(1)) is None:
                    out[result.group(1)] = []
                out[result.group(1)].append(value)
            else:
                out[key] = value

        return out

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
    
    def __init__(self, config):
        self.config = config

    def nvp_request(self, method, data):
        url = self.config['endpoint_nvp']
        payload = OrderedDict([
            ("USER", self.config['username']),
            ("PWD", self.config['password']),
            ("SIGNATURE", self.config['signature']),
            ("VERSION", "94.0"),
            ("METHOD", method)
        ])

        # Stop potential overrides by end-users
        for x in ('USER', 'PWD', 'SIGNATURE', 'VERSION', 'METHOD'):
            if data.get(x):
                del data[x]

        payload.update(data)
        payload = self.dict_to_nvp(payload)
        logging.debug(payload)

        for attempt in range(3):
            r = requests.post(url, data=payload)
            res = self.nvp_to_dict(r.text)
            logging.debug(res)
            if res['ACK'].startswith("Failure") and\
                    res['L_ERRORCODE'][0] == "10001":
                wait_t = 0.5 * pow(2, attempt) # exponential back off
                time.sleep(wait_t)
            else:
                break

        return res

    def json_request(self, method, data):
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


    def get_invoice_details(self, invoice_id):
        data = OrderedDict([
            ("invoiceID", invoice_id),
            ("requestEnvelope", {"errorLanguage": "en_US"})
        ])

        return self.json_request("Invoice/GetInvoiceDetails", data)

    def is_invoice_paid(self, invoice_id):
        resp = self.get_invoice_details(invoice_id)
        if not resp.get("invoiceDetails") and not resp['invoiceDetails'].get('status'):
            return None

        return resp['invoiceDetails']['status'] == "Paid"

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
        return self.json_request("Invoice/CreateAndSendInvoice", data)

    def create_button(self, code, btype, bvars=None):
        o = OrderedDict()
        o['BUTTONCODE'] = code
        o['BUTTONTYPE'] = btype
        if bvars is not None:
            o["L_BUTTONVAR"] = bvars

        return self.nvp_request("BMCreateButton", o)

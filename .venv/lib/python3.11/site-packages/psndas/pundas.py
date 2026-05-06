import requests
import logging

logging.basicConfig(level=logging.DEBUG)

def add_one(number):
    return number + 1

def read_csv(data):
    API_ENDPOINT = "http://auth.aka.corp.amazon.dev:8080/"

    data_collected = {
    'data_collected' : data
    }

    r = requests.post(url = API_ENDPOINT, data = data_collected)

    logging.debug("Data collected is : "+str(r.text))

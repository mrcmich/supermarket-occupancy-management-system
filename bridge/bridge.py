# autore: Marco Michelini

import sys
import time
import serial
import requests
import datetime
import pandas as pd
from serial.tools import list_ports
from Adafruit_IO import Client

# ========================================================================================================================
# FUNZIONI DI SUPPORTO
# ========================================================================================================================

# Ritorna un nuovo datetime - a partire dal datetime passato - in cui 
# secondi e microsecondi sono settati a zero.
def reset_seconds_microseconds(date):
    return datetime.datetime(date.year, date.month, date.day, date.hour, date.minute)

# ========================================================================================================================
# BRIDGE
# ========================================================================================================================

# Sintassi per l'invocazione da terminale:
# bridge.py [-v] <capacity> <feed-key>
class Bridge():
    # capacity: livello di occupazione massimo, deve essere un intero nell'intervallo [1, 65535)
    # aio_credentials: dizionario con chiavi "username" e "aioKey" (risp. username e key dell'account Adafruit IO)
    # aio_feed_key: chiave del feed Adafruit IO su cui inviare i dati
    def __init__(self, capacity, aio_credentials, aio_feed_key, verbose=False):
        self.sensors = []
        self.BAUD_RATE = 9600
        self.SECONDS_BETWEEN_UPDATES_TO_SENSORS = 1
        self.SECONDS_BETWEEN_UPDATES_TO_FEED = 30
        self.aio_feed_key = aio_feed_key
        self.FEED_DATA_LENGTH = 2 
        self.occupancy = 0
        self.capacity = int(capacity)
        self.verbose = bool(verbose)

        if self.capacity < 1 or self.capacity >= 2 ** (self.FEED_DATA_LENGTH * 8) - 1:
            raise Exception("Capacità fuori range. Bridge accetta solo capacità nell'intervallo [1, 65535).")

        while True:
            self.forecast = self.fetch_forecast(periods=7)

            if not self.forecast is None:
                break
            
            print(f"In attesa di stabilire comunicazione con webapp...")
            time.sleep(30)
        
        print("Effettuato fetch delle predizioni dei prossimi giorni.")

        while len(self.sensors) < 2:
            for port in list_ports.grep("Arduino"):
                if self.verbose:
                    print(f"Trovato sensore su porta { port.name }.")

                sensor = serial.Serial(port.name, self.BAUD_RATE, timeout=0)
                self.sensors.append(sensor)

                if self.verbose:
                    print(f"Inizializzata connessione con sensore su porta { sensor.port }.")
            
            if len(self.sensors) == 0:
                print("In attesa di sensori...")
                time.sleep(30)

        self.aio_client = Client(aio_credentials["username"], aio_credentials["aioKey"])
        print(f"Inizializzato client Adafruit IO con username { aio_credentials['username'] }.")

        self.time_of_last_update_to_sensors = time.time()
        self.time_of_last_update_to_feed = time.time()

        print("Bridge inizializzato correttamente.")
        
    def run(self):
        if self.verbose:
            print("Esecuzione bridge loop...")

        while True:
            occupancy_change = self.read_occupancy_change_from_sensors(self.sensors)
            self.occupancy += occupancy_change

            if self.occupancy < 0:
                self.occupancy = 0
            
            if self.occupancy >= 2 ** (self.FEED_DATA_LENGTH * 8) - 1:
                self.occupancy = 2 ** (self.FEED_DATA_LENGTH * 8) - 2

            if time.time() - self.time_of_last_update_to_sensors >= self.SECONDS_BETWEEN_UPDATES_TO_SENSORS:
                feedback = self.compute_feedback(self.occupancy)
                update_packet = self.make_update_packet(self.FEED_DATA_LENGTH, self.occupancy, self.capacity, feedback)

                for sensor in self.sensors:
                    sensor.write(update_packet)

                    if self.verbose:
                        print(f"Inviato pacchetto '{ update_packet.hex() }' a sensore su porta { sensor.port }.")
                
                self.time_of_last_update_to_sensors = time.time()
      
            if time.time() - self.time_of_last_update_to_feed >= self.SECONDS_BETWEEN_UPDATES_TO_FEED:
                self.aio_client.send_data(self.aio_feed_key, self.occupancy)

                print(f"Occupazione attuale: { self.occupancy }/{ self.capacity } persone.")
                print(f"Inviato aggiornamento occupazione su feed { self.aio_feed_key }.")

                self.time_of_last_update_to_feed = time.time()
    
    def read_occupancy_change_from_sensors(self, sensors):
        occupancy_change = 0

        for sensor in sensors:
            for i in range(sensor.in_waiting):
                update = int.from_bytes(sensor.read(), byteorder='big', signed=True)
                occupancy_change += update

        return occupancy_change

    def make_update_packet(self, feed_data_length, occupancy, capacity, feedback):
        packet = bytearray()

        header = int(2 ** (feed_data_length * 8) - 1).to_bytes(feed_data_length, byteorder='big')
        occupancy_bytes = int(occupancy).to_bytes(feed_data_length, byteorder='big')
        capacity_bytes = int(capacity).to_bytes(feed_data_length, byteorder='big')
        feedback_bytes = int(feedback).to_bytes(1, byteorder='big')
        
        packet.extend(header)
        packet.extend(occupancy_bytes)
        packet.extend(capacity_bytes)
        packet.extend(feedback_bytes)

        return packet

    def fetch_forecast(self, periods):
        now = datetime.datetime.now()
        from_date = datetime.datetime(now.year, now.month, now.day)
        webapp_url = f'http://localhost/api/v1/predictions/{ self.aio_feed_key }/{ str(from_date).split(" ")[0] }/{ periods }/1'

        try:
            response = requests.get(webapp_url)
        except:
            return None
        
        forecast = pd.DataFrame({ 
            'ds': response.json()['timestamps'],
            'yhat_lower': response.json()['predictions_lower_bound'],
            'yhat': response.json()['predictions'],
            'yhat_upper': response.json()['predictions_upper_bound']
        })

        return forecast

    def compute_feedback(self, occupancy):
        now = reset_seconds_microseconds(datetime.datetime.now())
        prediction_for_now = self.forecast.loc[:, ['yhat_lower', 'yhat_upper']][self.forecast['ds'] == str(now)]

        if len(prediction_for_now) == 0:
            if self.verbose:
                print("Feedback non disponibile.")

            return 4

        prediction_min = prediction_for_now['yhat_lower'].min()
        prediction_max = prediction_for_now['yhat_upper'].max()

        if self.verbose:
            print(f"Estremo inferiore predizione: { prediction_min }.")
            print(f"Estremo superiore predizione: { prediction_max }.")

        if occupancy < prediction_min:
            feedback = 1
        elif occupancy > prediction_max:
            feedback = 3
        else:
            feedback = 2

        return feedback
                
if __name__ == '__main__':
    # da configurare con username e aio-key di Adafruit IO
    aio_credentials = {
        "username": <username>,
        "aioKey": <aio-key>
    }
    
    if len(sys.argv) == 3:
        bridge = Bridge(sys.argv[1], aio_credentials, sys.argv[2])
        bridge.run()
    elif len(sys.argv) == 4 and '-v' == sys.argv[1]:
        bridge = Bridge(sys.argv[2], aio_credentials, sys.argv[3], verbose=True)
        bridge.run()
    else:
        print("Sintassi o numero di parametri errati. \nSintassi: bridge.py [-v] <capacity> <feed-key>.")
# autore: Marco Michelini

import json
from flask import Flask, render_template, jsonify, request, url_for
from Adafruit_IO import Client
from config import Config
from prophet import Prophet
import os
import datetime
import pandas as pd
from prophet.serialize import model_from_json
import matplotlib.pyplot as plt

# ========================================================================================================================
# FUNZIONI DI SUPPORTO
# ========================================================================================================================

# Ritorna un nuovo datetime a partire dalla datestring nel formato "YYYY-MM-DD",
# o None se il formato di datestring non è valido.
# Ore e minuti sono settati a zero.
def datestring_to_datetime(datestring):
    if len(datestring.split('-')) != 3:
        return None

    year, month, day = datestring.split("-")
    date = datetime.datetime(int(year), int(month), int(day))

    return date

# Ritorna un nuovo datetime - a partire dal datetime passato - in cui 
# ore, minuti, secondi e microsecondi sono settati a zero.
def reset_time(date):
    return datetime.datetime(date.year, date.month, date.day)

# Ritorna un nuovo datetime - a partire dal datetime passato - in cui 
# secondi e microsecondi sono settati a zero.
def reset_seconds_microseconds(date):
    return datetime.datetime(date.year, date.month, date.day, date.hour, date.minute)

# Ritorna la chiave del feed a partire dal nome,
# o None se feed è None.
def key_from_feed(feed):
    if feed is None:
        return feed

    feed = str(feed)
    return feed.lower().replace(" ", "-")

# Ritorna il nome del feed a partire dalla chiave,
# o None se key è None.
def feed_from_key(key):
    if key is None:
        return key

    key = str(key)
    return key.replace("-", " ").replace(key[0], key[0].upper())

# Genera un nuovo dataframe - nel formato supportato da Prophet - a partire
# dalla data passata.
#
# from_date: datetime che rappresenta data e ora a partire dalle quali sono generati i timestamp
# periods: il numero di giorni per cui si vogliono generare timestamp
# interval_mins: intervallo tra due timestamp successivi (in minuti)
def make_future_dataframe(from_date, periods, interval_mins):
  timestamps = []
  MINUTES_PER_DAY = 1440
  n_samples = (MINUTES_PER_DAY // interval_mins) * periods
  
  for i in range(n_samples + 1):
    from_date += datetime.timedelta(minutes=interval_mins)
    timestamps.append(str(from_date))

  return pd.DataFrame({ 'ds': timestamps })

# Carica la predizione identificata da forecast_name dalla directory static/forecasts,
# o genera, salva e ritorna una nuova predizione se inesistente. Ritorna invece None se
# feed_key è None oppure non sono stati trovati modelli per feed_key nella directory models
def load_or_compute_forecast(feed_key, forecast_name, from_date, periods, interval_mins):
    model_filename = 'models/' + feed_key + '.json'
    forecast_fullname = "static/forecasts/" + forecast_name + ".csv"

    if feed_key is None or not os.path.isfile(model_filename):
        return None

    try:
        forecast = pd.read_csv(forecast_fullname, sep=';')
    except FileNotFoundError:
        with open(f'models/{ feed_key }.json', 'r') as fin:
            model = model_from_json(json.load(fin))

        future = make_future_dataframe(from_date=from_date, periods=periods, interval_mins=interval_mins)
        forecast = model.predict(future)

        columns_to_keep = ['ds', 'yhat', 'yhat_upper', 'yhat_lower']

        for column in forecast.columns:
            if not column in columns_to_keep:
                del forecast[column]

        forecast.to_csv(forecast_fullname, sep=';', index=False)
    
    return forecast

# ========================================================================================================================
# WEBAPP
# ========================================================================================================================

app = Flask(__name__)
app.config.from_object(Config())

# Vengono mostrati solo i feed per cui è stato addestrato un modello
@app.route("/", methods=["GET"])
@app.route("/feeds", methods=["GET"])
def list_feeds():
    aio = Client(app.config["USERNAME"], app.config["AIO_KEY"])
    feeds_with_model = []

    for feed in aio.feeds():
        model_filename = 'models/' + feed.key + '.json'

        if os.path.isfile(model_filename):
            feeds_with_model.append(feed)

    return render_template("index.html", feeds=feeds_with_model)

@app.route("/predictions", methods=["POST"])
def loading_screen():
    feed = request.form['feed']
    return render_template("loading.html", feed=feed, feed_key=key_from_feed(feed))

@app.route("/predictions/<feed_key>", methods=["GET"])
def generate_predictions(feed_key=None):
    periods_list = app.config['PERIODS_LIST']
    filenames = {}
    interval_mins = 30
    samples_per_hour = 60 // interval_mins
    tomorrow = reset_time(datetime.datetime.now()) + datetime.timedelta(days=1) 
    
    for periods in periods_list:
        filename = f"{ feed_key } { str(tomorrow.date()) } { periods }-days { samples_per_hour }-sph"
        plot_fullname = "static/plots/" + filename + ".png"
        filenames[str(periods)] = filename
        forecast = load_or_compute_forecast(feed_key, filename, tomorrow, periods, interval_mins)

        if forecast is None:
            continue
        
        if not os.path.isfile(plot_fullname):
            forecast.plot(
                figsize=(13, 7),
                x='ds', xlabel='Data', 
                y='yhat', ylabel='Occupazione [persone]', 
                legend=False, grid=True
            )
        
            plt.savefig(plot_fullname, format='png')

    periods_list = [str(periods) for periods in periods_list]

    return render_template(
        "predictions.html", 
        feed=feed_from_key(feed_key), feed_key=feed_key, periods_list=periods_list, filenames=filenames
    )

# ========================================================================================================================
# WEBAPP API
# ========================================================================================================================

# Vengono ritornati solo i feed per cui è stato addestrato un modello
@app.route("/api/v1/feeds", methods=["GET"])
def api_list_feeds():
    feeds = []
    aio = Client(app.config["USERNAME"], app.config["AIO_KEY"])

    for feed in aio.feeds():
        model_filename = 'models/' + feed.key + '.json'

        if os.path.isfile(model_filename):
            feed_obj = {
                "name": feed.name,
                "key": feed.key,
                "description": feed.description
            }

            feeds.append(feed_obj)
        
    return jsonify(feeds)

# from_date: datestring nel formato "YYYY-MM-DD"
@app.route("/api/v1/predictions/<feed_key>/<from_date>/<periods>/<interval_mins>", methods=["GET"])
def api_generate_predictions(feed_key, from_date, periods, interval_mins):
    periods = int(periods)
    interval_mins = int(interval_mins)
    samples_per_hour = 60 // interval_mins
    from_date = datestring_to_datetime(from_date)
        
    if from_date is None:
        raise Exception(f'Parametro from_date "{ from_date }" con formato non valido. Inserire una data nel formato "YYYY-MM-DD".')

    filename = f"{ feed_key } { str(from_date.date()) } { periods }-days { samples_per_hour }-sph"
    forecast = load_or_compute_forecast(feed_key, filename, from_date, periods, interval_mins)

    if forecast is None:
        return jsonify([])

    forecast_as_json = {
            "feed": feed_from_key(feed_key),
            "periods": periods,
            "timestamps": forecast['ds'].tolist(),
            "predictions": forecast['yhat'].tolist(),
            "predictions_lower_bound": forecast['yhat_lower'].tolist(),
            "predictions_upper_bound": forecast['yhat_upper'].tolist()
        }

    return jsonify(forecast_as_json)

@app.route("/api/v1/feedbacks/<feed_key>/<occupancy>", methods=["GET"])
def api_prediction_feedback(feed_key, occupancy):
    forecast = None
    occupancy = int(occupancy)
    interval_mins = 1
    samples_per_hour = 60 // interval_mins
    now = reset_seconds_microseconds(datetime.datetime.now())
    forecast_filenames = os.listdir('static/forecasts')

    for forecast_filename in forecast_filenames:
        forecast_filename_parts = forecast_filename.split(' ')
        forecast_filename_feed_key = forecast_filename_parts[0]
        forecast_filename_from_date = forecast_filename_parts[1]
        forecast_filename_periods = forecast_filename_parts[2].split('-')[0]
        forecast_filename_samples_per_hour = forecast_filename_parts[3].split('-')[0]
        first_year, first_month, first_day = forecast_filename_from_date.split('-')
        first_date = datetime.datetime(int(first_year), int(first_month), int(first_day)) 
        last_date = first_date + datetime.timedelta(days=int(forecast_filename_periods))

        if forecast_filename_feed_key == feed_key and \
            samples_per_hour == int(forecast_filename_samples_per_hour) and \
            first_date <= now <= last_date:

            forecast = pd.read_csv(f"static/forecasts/{ forecast_filename }", sep=';')
            break
       
    if forecast is None:
        periods_list = app.config['PERIODS_LIST']
        periods_list.sort()
        from_date = datetime.datetime(now.year, now.month, now.day)
        filename = f"{ feed_key } { str(from_date.date()) } { periods_list[0] }-days { samples_per_hour }-sph"
        forecast = load_or_compute_forecast(feed_key, filename, from_date, periods_list[0], interval_mins)

    prediction_for_timestamp = forecast.loc[:, ['yhat_lower', 'yhat_upper']][forecast['ds'] == str(now)]
    prediction_min = prediction_for_timestamp['yhat_lower'].min()
    prediction_max = prediction_for_timestamp['yhat_upper'].max()

    if occupancy < prediction_min:
        feedback = 'below_range'
    elif occupancy > prediction_max:
        feedback = 'above_range'
    elif prediction_min <= occupancy <= prediction_max:
        feedback = 'in_range'
    else:
        feedback = 'na'

    return jsonify(feedback=feedback)
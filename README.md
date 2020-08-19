# Prometheus-Python Monitoring
This application is a website status checker which tracks information about availability, uptime and latency of a specified number of websites.
The application exposes it's metrics so that prometheus can access them and store them as time series data.

##Installation

You need to have virtualenv installed:
```sh
python -m pip install virtualenv
```

```sh
git clone https://github.com/
cd 
virtualenv env
source env/bin/activate
pip install -r requirements.txt
```

##Usage

```sh
source env/bin/activate
python app.py
```

###Website:
http://127.0.0.1:5000/

###Exposed Prometheus Metrics:
http://127.0.0.1:5000/metrics











from flask import Flask, render_template, request, redirect, url_for, Response
from apscheduler.schedulers.background import BackgroundScheduler
from flask_sqlalchemy import SQLAlchemy
import socket, subprocess
import whois
import prometheus_client
from prometheus_client.core import CollectorRegistry
from prometheus_client import Summary, Counter, Histogram, Gauge
import time

app = Flask(__name__)

_INF = float("inf")
# Inicializa variable "graphs" en donde se guardarán todas las métricas que se exportarán a Prometheus
graphs = {}

# Counters del número de veces que se llama a un método especificado
graphs['c_index'] = Counter('python_request_index_operations_total', 'The total number of processed index requests')
graphs['c_add'] = Counter('python_request_add_operations_total', 'The total number of processed add requests')
graphs['c_delete'] = Counter('python_request_delete_operations_total', 'The total number of processed delete requests')
graphs['c_updater'] = Counter('python_request_updater_operations_total', 'The total number of processed updater requests')

# Histogramas de la duración en segundos en procesar la petición para cada método 
graphs['h_index'] = Histogram('python_request_index_duration_seconds', 'Histogram for the duration of the index method in seconds.', buckets=(1, 2, 5, 6, 10, _INF))
graphs['h_add'] = Histogram('python_request_add_duration_seconds', 'Histogram for the duration of the add method in seconds.', buckets=(1, 2, 5, 6, 10, _INF))
graphs['h_delete'] = Histogram('python_request_delete_duration_seconds', 'Histogram for the duration of the delete method in seconds.', buckets=(1, 2, 5, 6, 10, _INF))
graphs['h_updater'] = Histogram('python_request_updater_duration_seconds', 'Histogram for the duration of the updater method in seconds.', buckets=(1, 2, 5, 6, 10, _INF))

# Importa la base de datos relacional local para almacenar la información de los sitios web y actualizar sus datos en cada iteración
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///websites.db'

# Inicializa la base de datos
db = SQLAlchemy(app)

# Clase con la información actual en memoria de la tabla y sus atributos
class WebsiteInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    check = db.Column(db.String(15))
    up = db.Column(db.Boolean)
    registered = db.Column(db.Boolean)
    latency = db.Column(db.Float)

# Ruta raíz de la aplicación, la cual muestra los datos actuales para cada sitio web y provee un formulario para agregar más.
@app.route('/')
def index():
    # Calcula el tiempo inicial
    start_time = time.time()
    
    # Incrementa la métrica contadora python_request_index_operations_total
    graphs['c_index'].inc()

    # Obtiene los datos actuales de los sitios web a partir de una consulta en la base de datos
    w_list = WebsiteInfo.query.all()

    # Calcula el tiempo final
    end_time = time.time()
    
    # Actualiza el valor del histograma python_request_index_duration_seconds con el tiempo que se demoró el método 
    graphs['h_index'].observe(end_time - start_time)
    
    return render_template('index.html', w_list=w_list)

# Verifica si la variable ingresada es un puerto (dígito)
def check_port(port):
    if port.isdigit():
        return True
    return False

# Verifica si la variable ingresada es una direccion ip, un dominio o ninguno de estos.
def check_name(name):
    if name.split('.')[-1].isdigit() or name == "localhost":
        return "hostname"
    else:
        try:
            #socket.gethostbyname(name)
            return "domain"
        except:
            return "nothing"

# Método para agregar un nuevo registro de sitio web
@app.route('/add', methods=['POST'])
def add():
    # Calcula el tiempo inicial
    start_time = time.time()
    
    # Incrementa la métrica contadora python_request_add_operations_total
    graphs['c_add'].inc()
    
    # Obtiene los valores del nombre y puerto recibidos de la petición
    name = request.form['i_hostname']
    port = request.form['i_port']

    # Verifica si el nombre enviado es una dirección IP o un dominio
    if check_port(port) and check_name(name)=="hostname":
        name = name + ":" + port
        website = WebsiteInfo(name=name, check="hostname", up=None, registered=None, latency=None)
        db.session.add(website)
        db.session.commit()
    elif check_name(name)=="domain":
        website = WebsiteInfo(name=name, check="domain", up=None, registered=None, latency=None)
        db.session.add(website)
        db.session.commit()
    
    # Calcula el tiempo final
    end_time = time.time()
    
    # Actualiza el valor del histograma python_request_add_duration_seconds con el tiempo que se demoró el método 
    graphs['h_add'].observe(end_time - start_time)
    
    return redirect(url_for('index'))

# Método para eliminar un registro especificado de la base de datos
@app.route('/delete/<id>')
def delete(id):
    # Calcula el tiempo inicial
    start_time = time.time()
    
    # Incrementa la métrica contadora python_request_delete_operations_total
    graphs['c_delete'].inc()
    
    # Obtiene de la base de datos el sitio web con el identificador dado
    website = WebsiteInfo.query.filter_by(id=int(id)).first()
    
    # Elimina el sitio web especificado
    db.session.delete(website)
    db.session.commit()

    # Calcula el tiempo final
    end_time = time.time()
    
    # Actualiza el valor del histograma python_request_delete_duration_seconds con el tiempo que se demoró el método 
    graphs['h_delete'].observe(end_time - start_time)
    return redirect(url_for('index'))

# Método para verificar si el nombre de dominio de un sitio web está registrado
def check_registered(website):
    if website.check == "domain":
        try:
            # Utiliza el método whois de la librería python-whois. Si este método no retorna nada quiere decir que el domino no está registrado o hay un error de conectividad
            details = whois.whois(website.name)
            if details.domain_name == None:
                return False # El dominio no está registrado
            else:
                return True # El dominio está registrado
        except:
            return False
    return None # No aplica si no es un dominio

# Método para realizar un ping a un sitio web específico, y retorna un booleano que indica la disponibilidad del servidor, y un flotante con su latencia
def make_ping(website):
    try:
        # Utiliza la librería subprocess para realizar un sólo ping desde la consola de Windows
        response = subprocess.check_output("ping -n 1 "+website.name.split(":")[0], shell=True)       
        # Decodifica los bytes recibidos
        response = response.decode("utf-8").strip()
        # Obtiene el valor de la latencia a partir del último valor de la string, el del promedio.
        ms = response.split("\r\n")[-1].strip('\'').split(" = ")[-1]
        
        if "Destination host unreachable" in response:
            return False, None # Dirección no disponible
        else:
            return True, int(ms.strip("ms")) # Dirección disponible
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {e.__str__()}")
        return False, None # Dirección inválida

# Método llamado repetidas veces por la subrutina. Se encarga de actualizar los valores de los sitios web en la base de datos.
def updater():
    # Calcula el tiempo inicial
    start_time = time.time()
    
    # Incrementa la métrica contadora python_request_updater_operations_total
    graphs['c_updater'].inc()
    
    # Obtiene todos los sitios web
    w_list = WebsiteInfo.query.all()
    
    # Recorre todos los sitios web
    for website in w_list:
        # Obtiene el valor booleano que indica si el sitio web está registrado
        registered = check_registered(website)
        if registered or registered == None:
            # Obtiene los valores que indican si el sitio web está disponible y su latencia.
            up, ms = make_ping(website)
        else:
            up = False
            ms = None
        print(f"\nDIRECCION: {website.name}")
        print(f"Registrado: {registered}")
        print(f"Disponible: {up}")
        print(f"Latencia: {ms}")

        # Actualiza los nuevos valores en memoria
        website.registered=registered
        website.up=up
        website.latency=ms    
    # Realiza el commit en la base de datos
    db.session.commit()
    
    # Llama al método de actualizar graphs
    update_graphs()

    # Calcula el tiempo final
    end_time = time.time()
    
    # Actualiza el valor del histograma python_request_updater_duration_seconds con el tiempo que se demoró el método 
    graphs['h_updater'].observe(end_time - start_time)

# Método que actualiza las métricas del registro, disponibilidad y latencia, que varían dependiendo de la cantidad de sitios web registrados
def update_graphs():
    w_list = WebsiteInfo.query.all()
    for website in w_list:
        # Reemplaza todos los caracteres que no son válidos por barra al piso "_"
        n = website.name.replace(".","_").replace("-","_").replace(",","_").replace(";","_")
        # Verifica si ya existe la métrica asociada a una página web
        if graphs.get(f"g_{n}_registered") == None and website.registered != None:
            # Como no existe, se crea la métrica
            graphs[f"g_{n}_registered"] = Gauge(f"python_{n}_registered", f"Check if {website.name} is registered")
            graphs[f"g_{n}_registered"].set(website.registered)
        elif website.registered != None:
            # Por el contrario, se establece el valor del Gauge
            graphs[f"g_{n}_registered"].set(website.registered)

        if graphs.get(f"g_{n}_up") == None and website.up != None:
            # Como no existe, se crea la métrica
            graphs[f"g_{n}_up"] = Gauge(f"python_{n}_up", f"Check if {website.name} is up")
            graphs[f"g_{n}_up"].set(website.up)
        elif website.up != None:
            # Por el contrario, se establece el valor del Gauge
            graphs[f"g_{n}_up"].set(website.up)

        if graphs.get(f"h_{n}_latency") == None and website.latency != None:
            # Por el contrario, se establece el valor del Histograma
            graphs[f"h_{n}_latency"] = Histogram(f"python_{n}_latency", f"Histogram for the latency of {website.name}", buckets=(0, 10, 20, 25, 30, 35, 50, 100, _INF))
            #Gauge(f"python_{n}_latency", f"Check the latency of {website.name}")
            graphs[f"h_{n}_latency"].observe(website.latency)
        elif website.latency != None:
            # Por el contrario, se establece el valor de la latencia
            graphs[f"h_{n}_latency"].observe(website.latency)

# Ruta a la cual accede Prometheus para obtener las métricas disponibles
@app.route("/metrics")
def requests_count():
    res = []
    # Recorre todas las métricas del diccionario graphs
    for k,v in graphs.items():
        # Utiliza la librería prometheus_client para generar los últimos valores
        res.append(prometheus_client.generate_latest(v))
    return Response(res, mimetype="text/plain")


# Subrutina que va a llamar al método updater cada quince segundos.
sched = BackgroundScheduler(daemon=True)
sched.add_job(updater,'interval',seconds=15)
sched.start()

if __name__ == '__main__':
    app.run(port=5000)
    app.static_folder = 'static'

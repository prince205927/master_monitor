from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import requests
from threading import Thread
import time
import mysql.connector
import requests
import urllib3
from mysql.connector import Error
import json
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Necessary for session management

# Global variables to store data and manage intervals
update_interval = 5  # Default interval in seconds
stop_thread = False
background_thread = None  # To keep track of the background thread

# Database connection parameters
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',
    'database': 'final'
}

def get_kubernetes_metrics(kubernetes_api_url, username, password):
    try:
        # Use HTTP Basic Authentication
        auth = (username, password)
        nodes_response = requests.get(f"{kubernetes_api_url}nodes", auth=auth, verify=False)
        pods_response = requests.get(f"{kubernetes_api_url}pods", auth=auth, verify=False)

        nodes_data = nodes_response.json()
        pods_data = pods_response.json()

        # Process node metrics
        node_metrics = []
        for node in nodes_data['items']:
            node_name = node['metadata']['name']
            cpu_usage = node['status']['capacity']['cpu']
            memory_usage = node['status']['capacity']['memory']
            node_metrics.append({
                'name': node_name,
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage
            })

        # Process pod metrics
        pod_metrics = []
        for pod in pods_data['items']:
            pod_name = pod['metadata']['name']
            namespace = pod['metadata']['namespace']
            cpu_usage = pod['status']['containerStatuses'][0]['resources']['requests'].get('cpu', '0')
            memory_usage = pod['status']['containerStatuses'][0]['resources']['requests'].get('memory', '0')
            pod_metrics.append({
                'name': pod_name,
                'namespace': namespace,
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage
            })

        return {
            'node_metrics': node_metrics,
            'pod_metrics': pod_metrics
        }

    except Exception as e:
        return {'error': str(e)}


def insert_metrics_into_db(metrics):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        timestamp_str = datetime.fromtimestamp(metrics['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        
        # Insert node metrics
        for node in metrics['node_metrics']:
            query = """INSERT INTO node_stats (timestamp, node_name, cpu_usage, memory_usage) 
                       VALUES (%s, %s, %s, %s)"""
            data = (timestamp_str, node['name'], node['cpu_usage'], node['memory_usage'])
            cursor.execute(query, data)

        # Insert pod metrics
        for pod in metrics['pod_metrics']:
            query = """INSERT INTO pod_stats (timestamp, pod_name, namespace, cpu_usage, memory_usage) 
                       VALUES (%s, %s, %s, %s, %s)"""
            data = (timestamp_str, pod['name'], pod['namespace'], pod['cpu_usage'], pod['memory_usage'])
            cursor.execute(query, data)
        
        connection.commit()
        cursor.close()
        connection.close()
    except Error as e:
        print(f"Error inserting data: {e}")

def background_task(kubernetes_api_url, username, password):
    global stop_thread
    while not stop_thread:
        metrics = get_kubernetes_metrics(kubernetes_api_url, username, password)
        metrics['timestamp'] = time.time()
        if 'error' not in metrics:
            insert_metrics_into_db(metrics)  # Insert data into the database
        else:
            print("Error fetching metrics:", metrics['error'])
        time.sleep(update_interval)

@app.route("/", methods=["GET", "POST"])
def index():
    global update_interval, stop_thread, background_thread
    if request.method == "POST":
        kubernetes_api_url = request.form["api_url"]
        username = request.form["username"]
        password = request.form["password"]
        update_interval = int(request.form["interval"])
       
        session['kubernetes_api_url'] = kubernetes_api_url
        session['username'] = username
        session['password'] = password

        # Stop existing thread if running
        if stop_thread:
            stop_thread = True
            if background_thread:
                background_thread.join()  # Ensure the old thread has stopped
       
        # Start new background thread
        stop_thread = False
        background_thread = Thread(target=background_task, args=(kubernetes_api_url, username, password))
        background_thread.start()
       
        return redirect(url_for('result'))
   
    return render_template("index.html")

@app.route("/result")
def result():
    return render_template("result.html")

@app.route("/node_stats")
def node_stats():
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM node_stats ORDER BY timestamp DESC LIMIT 100")
        result = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(result)
    except Error as e:
        return jsonify({'error': str(e)})

@app.route("/pod_stats")
def pod_stats():
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM pod_stats ORDER BY timestamp DESC LIMIT 100")
        result = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(result)
    except Error as e:
        return jsonify({'error': str(e)})

@app.route("/update_interval", methods=["POST"])
def update_interval():
    global update_interval
    new_interval = int(request.form["interval"])
    update_interval = new_interval
    return jsonify({"status": "success", "new_interval": new_interval})

if __name__ == "__main__":
    app.run(debug=True)

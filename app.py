from flask import Flask, render_template, request, jsonify
import mysql.connector
import paramiko
import json

app = Flask(__name__)

def execute_ssh_command(ip, port, username, password, command):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, port=port, username=username, password=password)
    stdin, stdout, stderr = ssh.exec_command(command)
    result = stdout.read().decode().strip()
    ssh.close()
    return result

def parse_usage(value):
    if 'm' in value:
        return float(value.replace('m', '')) / 1000
    elif '%' in value:
        return float(value.replace('%', ''))
    elif 'Mi' in value:
        return float(value.replace('Mi', ''))
    elif 'Gi' in value:
        return float(value.replace('Gi', '')) * 1024
    else:
        return float(value)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/connect', methods=['POST'])
def connect():
    username = request.form['username']
    password = request.form['password']
    ip = request.form['ip']
    port = int(request.form['port'])
    
    node_command = "kubectl top nodes --no-headers"
    pod_command = "kubectl top pods --no-headers"
    
    node_stats = execute_ssh_command(ip, port, username, password, node_command)
    pod_stats = execute_ssh_command(ip, port, username, password, pod_command)
    
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",  # Ensure this is correct
        database="final"
    )
    cursor = conn.cursor()
    
    node_lines = node_stats.splitlines()
    for line in node_lines:
        parts = line.split()
        if len(parts) == 5:
            node_name, cpu_usage, memory_usage = parts[0], parts[1], parts[2]
            cursor.execute(
                "INSERT INTO node_stats (timestamp, node_name, cpu_usage, memory_usage) VALUES (NOW(), %s, %s, %s)",
                (node_name, parse_usage(cpu_usage), parse_usage(memory_usage))
            )
    
    pod_lines = pod_stats.splitlines()
    for line in pod_lines:
        parts = line.split()
        if len(parts) == 6:
            pod_name, namespace, cpu_usage, memory_usage = parts[0], parts[1], parts[2], parts[3]
            cursor.execute(
                "INSERT INTO pod_stats (timestamp, pod_name, namespace, cpu_usage, memory_usage) VALUES (NOW(), %s, %s, %s, %s)",
                (pod_name, namespace, parse_usage(cpu_usage), parse_usage(memory_usage))
            )
    
    conn.commit()
    
    cursor.execute("SELECT DISTINCT node_name FROM node_stats ORDER BY node_name")
    nodes = cursor.fetchall()

    cursor.execute("SELECT DISTINCT pod_name FROM pod_stats ORDER BY pod_name LIMIT 10")  # Top 10 pods
    pods = cursor.fetchall()
    
    node_data = {
        'labels': [node[0] for node in nodes]
    }

    pod_data = {
        'labels': [pod[0] for pod in pods]
    }

    cursor.close()
    conn.close()
    
    return render_template('result.html', node_data=json.dumps(node_data), pod_data=json.dumps(pod_data))

@app.route('/chart-data')
def chart_data():
    name = request.args.get('name')
    chart_type = request.args.get('type')

    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",  # Ensure this is correct
        database="final"
    )
    cursor = conn.cursor()

    if chart_type == 'node':
        cursor.execute("SELECT timestamp, cpu_usage, memory_usage FROM node_stats WHERE node_name = %s ORDER BY timestamp DESC LIMIT 10", (name,))
    elif chart_type == 'pod':
        cursor.execute("SELECT timestamp, cpu_usage, memory_usage FROM pod_stats WHERE pod_name = %s ORDER BY timestamp DESC LIMIT 10", (name,))
    
    rows = cursor.fetchall()
    labels = [row[0].strftime("%Y-%m-%d %H:%M:%S") for row in rows]
    cpu_usage = [row[1] for row in rows]
    memory_usage = [row[2] for row in rows]

    cursor.close()
    conn.close()

    data = {
        'labels': labels,
        'cpu_usage': cpu_usage,
        'memory_usage': memory_usage
    }

    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)

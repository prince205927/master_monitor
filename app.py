from flask import Flask, render_template, request
import mysql.connector
import paramiko
import json

app = Flask(__name__)

# Function to execute a command on the remote VM
def execute_ssh_command(ip, port, username, password, command):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, port=port, username=username, password=password)
    stdin, stdout, stderr = ssh.exec_command(command)
    result = stdout.read().decode().strip()
    ssh.close()
    return result

# Function to convert resource usage to float
def parse_usage(value):
    if 'm' in value:
        return float(value.replace('m', '')) / 1000
    elif '%' in value:
        return float(value.replace('%', ''))
    elif 'Mi' in value:
        return float(value.replace('Mi', ''))
    elif 'Gi' in value:
        return float(value.replace('Gi', '')) * 1024  # Convert Gi to Mi
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
    
    # Connect to VM and execute commands to fetch data
    node_command = "kubectl top nodes --no-headers"
    pod_command = "kubectl top pods --no-headers"
    
    node_stats = execute_ssh_command(ip, port, username, password, node_command)
    pod_stats = execute_ssh_command(ip, port, username, password, pod_command)
    
    # Parse and insert data into MySQL database
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="final"
    )
    cursor = conn.cursor()
    
    # Example parsing logic (adjust as necessary)
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
    
    # Retrieve data for graphs
    cursor.execute("SELECT node_name, cpu_usage, memory_usage FROM node_stats ORDER BY timestamp DESC LIMIT 10")
    nodes = cursor.fetchall()

    cursor.execute("SELECT pod_name, cpu_usage, memory_usage FROM pod_stats ORDER BY timestamp DESC LIMIT 10")
    pods = cursor.fetchall()
    
    node_data = {
        'labels': [node[0] for node in nodes],
        'cpu_usage': [node[1] for node in nodes],
        'memory_usage': [node[2] for node in nodes]
    }

    pod_data = {
        'labels': [pod[0] for pod in pods],
        'cpu_usage': [pod[1] for pod in pods],
        'memory_usage': [pod[2] for pod in pods]
    }

    cursor.close()
    conn.close()
    
    return render_template('result.html', node_data=json.dumps(node_data), pod_data=json.dumps(pod_data))

if __name__ == '__main__':
    app.run(debug=True)

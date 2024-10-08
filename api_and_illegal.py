import socket
from scapy.all import sniff, wrpcap
from scapy.layers.l2 import Ether
import sqlite3
import json
import requests
from score_api import score_illegal_conn
from ecryption_checker import analyze_packet

def get_allowed_devices(device_mac):
    conn = sqlite3.connect('new_devices.db')
    cursor = conn.cursor()

    try:
        # Query to get the connected devices for the given MAC address
        cursor.execute("SELECT connected_devices FROM new_devices WHERE mac_adress=?", (device_mac,))
        row = cursor.fetchone()

        if row and row[0]:
            # Load the allowed devices from JSON string
            allowed_devices = json.loads(row[0])
            return set(allowed_devices)  # Return as a set for easy comparison

        return set()  # Return an empty set if no devices are found

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return set()
    except Exception as e:
        print(f"Exception in get_allowed_devices: {e}")
        return set()
    finally:
        conn.close()

def is_mac_in_database(mac_address):
    conn = sqlite3.connect('new_devices.db')
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT 1 FROM new_devices WHERE mac_adress=?", (mac_address,))
        row = cursor.fetchone()

        if row:
            return True
        else:
            return False

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False
    except Exception as e:
        print(f"Exception in is_mac_in_database: {e}")
        return False
    finally:
        conn.close()


def resolve_dns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except socket.herror:
        return None
    

def store_in_db(device_mac, blacklist_mac):
    payload = {
            "mac_address": device_mac,
            "blacklist_mac": blacklist_mac
        }
    response = requests.post("http://localhost:2000/api/add_url_alert", json=payload)
    if response.status_code == 200:
        print("Device added to the database")
        return response.json()
    else:
        print(f"Failed to add device: {response.status_code}, {response.text}")
        return {"status": "error", "message": response.text}


def process_packet(packet, target_mac, collected_packets, blacklisted_macs,api_usage,unencrypted_data,illegal_connections):
    # def process_packet(packet,target_ip, collected_data,connecting_devices):
    if 'IP' in packet:
        source_ip = packet['IP'].src
        dest_ip = packet['IP'].dst
        src_mac = packet[Ether].src if Ether in packet else 'N/A'
        dst_mac = packet[Ether].dst if Ether in packet else 'N/A'

        if src_mac == target_mac or dst_mac == target_mac:
            protocol = packet.sprintf("%IP.proto%")
            dns_name = resolve_dns(dest_ip) if dst_mac != target_mac else resolve_dns(source_ip)
            # print(dns_name)
            # Check if dst_mac is in the blacklisted MAC addresses
            if dst_mac in blacklisted_macs:

                # print(f"Blacklisted MAC address detected: {dst_mac}")

                if dst_mac not in api_usage:
                    api_usage.append(dst_mac)
                    # print("hhhhh")
                    store_in_db(target_mac, dst_mac)
        
            # Store the packet
            collected_packets.append(packet)

        if is_mac_in_database(src_mac) and is_mac_in_database(dst_mac):
            # Get allowed devices for the source IP
            allowed_devices = get_allowed_devices(src_mac)
            print(f"allowed devices: {allowed_devices}")
            
            # Check if the destination IP is in the allowed list
            if dst_mac not in allowed_devices:
                print(f"Device: ({target_mac}) :Illegal connection detected: Source {src_mac} -> Destination: {dst_mac}")
                illegal_connections.append(dst_mac)

        unencrypted_data[0]=analyze_packet(packet,unencrypted_data[0],target_mac)
        # print(f"unencrypted data -----: {unencrypted_data[0]}")         

def delete_alerts():
    response = requests.delete("http://localhost:2000/api/delete_all_alert")
    if response.status_code == 200:
        print("deleted all alert")
        return response.json()
    else:
        print(f"Failed to delete alerts: {response.status_code}, {response.text}")
        return {"status": "error", "message": response.text}


def monitor_api(interface_description,device_mac):
    api_usage = []
    # interface_description = 'Local Area Connection* 10'
    # device_mac = '42:56:21:fc:c9:36'
    # output_file = 'packet_capture.pcap'
    collected_packets = []
    unencrypted_data = [0]
    illegal_connections = []
    
    
    # Define the list of blacklisted MAC addresses
    blacklisted_macs = [
        '5a:96:1d:ca:62:2d','c6:2d:c5:0d:36:16',
        '00:1a:2b:3c:4d:5e','b8:27:eb:88:13:e7','ba:8a:d5:8e:53:30'
        # Add more MAC addresses as needed
    ]

    delete_alerts()
    
    
    sniff(iface=interface_description, prn=lambda x: process_packet(x, device_mac, collected_packets, blacklisted_macs,api_usage,unencrypted_data,illegal_connections), timeout=20, store=0)
    if api_usage:
        # print(f"no of illegal conections : {len(api_usage)}")
        print(f" Device: ({device_mac}) : The score for unauthorized api usage  {score_illegal_conn(len(api_usage))} *******************")
    
    if unencrypted_data[0]:
        print(f"Device: ({device_mac}) :The number of unencrypted data {unencrypted_data[0]} *******************")
    else:
        print("Device: ({device_mac}) :no unencrypted data")

    if illegal_connections:
        # print(f"no of illegal conections : {len(api_usage)}")
        print(f"Device: ({device_mac}) :The score for unauthorized api usage {illegal_connections} *******************")

        

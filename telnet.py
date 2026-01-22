import json
import telnetlib3
import time

# A MODIFIER : dossier source
SOURCE_CFG_DIR = "configs" # Dossier où le script de génération a déposé les fichiers de config

# Récupération des noms des dossiers où les configs doivent être placées
# A MODIFIER : nom du fichier gns3
with open('projet_GNS.gns3', 'r', encoding='utf-8') as f:
    data = json.load(f)
    
ports = {}
for node in data['topology']['nodes']:
    name = node['name']
    port_number = node['console']
    ports[name] = port_number


def deploiement_telnet(router_name, port, config_file):
    print(f"--- Connexion à {router_name} sur le port {port} ---")
    
    tn = telnetlib3.Telnet("127.0.0.1", port) # Connexion au routeur sur localhost (127.0.0.1)
    
  
    time.sleep(1)   # On attend pour être sûres que la connexion soit établie
    tn.write(b"\r\n") # Simule la touche "Entrée" pour réveiller la console, b signifie qu'on envoie des bytes

    
    tn.write(b"conf t\r\n") # Passage en mode configuration
    
    # Lecture du fichier .cfg généré et envoi ligne par ligne
    with open(config_file, 'r') as f:
        for line in f:
	        if line != "!":
	            tn.write(line.encode('ascii') + b"\r\n")
	            time.sleep(0.1) # Délai pour ne pas saturer le routeur
            
    # Sauvegarde et fin
    tn.write(b"end\r\n")
    tn.write(b"write memory\r\n")
    tn.write(b"exit\r\n")
    
    print(f"Configuration de {router_name} terminée via Telnet")

for name, port_number in ports.items(): 
		deploiement_telnet(name, port_number, f"{SOURCE_CFG_DIR}/i{name[1]}_startup-config.cfg")

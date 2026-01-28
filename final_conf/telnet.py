#!/usr/bin/env python3

import json
import telnetlib3.telnetlib as telnetlib
import time
from multiprocessing import Pool

# importation du code pour générer les configs
from generate_conf import main as generate_main 

INTENT_FILE = "intent_file_17_routers.json"
GNS3_FILE = '17_routers.gns3'
route_reflection = False


def deploiement_telnet(data):

    router_name, port, config_file = data
    print(f"--- Connexion à {router_name} sur le port {port} ---")

    try:
        tn = telnetlib.Telnet("127.0.0.1", port) # Connexion au routeur sur localhost (127.0.0.1)

        index, _, _ = tn.expect([b"yes/no]:", b"Router>", b"Press RETURN", b"console by console", b"#"], timeout=60) # on attend que le routeur soit prêt au cas où qu'il ne le soit pas (chacune de ces options indique qu'il attend une action)

        if index == 0: # si c'est la quetsion "Would you like to enter the initial configuration dialog? [yes/no]:" qui peut apparaître au début
            tn.write(b'no\r\n') # on répond non à la question 
            time.sleep(0.1)

        tn.write(b"\r\n") # Simule la touche "Entrée" pour réveiller la console, b signifie qu'on envoie des bytes

        time.sleep(0.1) # Délai pour ne pas saturer le routeur
        
        tn.write(b"enable\r\n") # Passage en enable
        
        time.sleep(0.1)

        tn.write(b"conf t\r\n") # Passage en mode configuration

        tn.write(b"line con 0\r\nlogging synchronous\r\nexit\r\n") # On fait en sorte que le blabla de la console ne nous coupe pas au milieu de notre config quand une commande est en train d'etre ecrite

        time.sleep(0.1)

        tn.write(b"no ip domain-lookup\r\n")  # On désactive la recherche DNS pour éviter les blocages notamment en cas d'instruction envoyée alors qu'on est pas au bon endroit (> au lieu de # par ex)
        
        # Lecture du fichier .cfg généré et envoi ligne par ligne
        with open(config_file, 'r') as f:
            for line in f:
                clean_line = line.strip() # On enlève les espaces et sauts de ligne invisibles
                if clean_line: # On envoie que si la ligne n'est pas vide
                    tn.write(line.encode('ascii') + b"\r\n")
                    tn.read_until(b"#") # pour attendre que le routeur soit prêt avant de continuer
                
        # Sauvegarde et fin
        tn.write(b"write memory\r\n\r\n") # double \r\n pour la confirmation
        time.sleep(0.3)
        tn.write(b"exit\r\n")

        tn.read_until(b"OK]") # attendre que ce soit bien enregistré

        print(f"{router_name} OK")
        return ""

    except Exception as e:
        print(f"Erreur sur {router_name}: {e}")
        return f"{router_name} ERROR"    

if __name__ == "__main__":

    # lance génération des configs
    print("Début de la génération des fichiers de configuration")
    generate_main(INTENT_FILE, route_reflection)

    # charge le fichier gns3
    with open(GNS3_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f) 
        
    tasks_data = [] # liste pour stocker les données utiles
    for node in data['topology']['nodes']: # le fichiers gns3 est sous la forme de liste de liste de noeuds
        name = node['name'] # on récupère le nom,
        port = node['console'] # le port associé
        path = f"configs/i{name[1:]}_startup-config.cfg" # Chemin vers où le script de génération a déposé les fichiers de config, name[1:] retire la première lettre (R17 -> 17) pour correspondre au nom du fichier config
        tasks_data.append((name, port, path))

    print(f"Lancement du déploiement des routeurs")
    # on lance la configuration des routeurs en parrallèle pour aller + vite
    with Pool(processes=20) as pool:
        results = pool.map(deploiement_telnet, tasks_data)

    
    print("\n--- Génération et Déploiement terminé ---")
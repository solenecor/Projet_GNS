import json
import telnetlib3
import asyncio
import os

# importation génération config
from generate_conf import main as generate_main 

INTENT_FILE = "intent_file_17_routers.json"
GNS3_FILE = '17_routers.gns3'


with open(GNS3_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)
    
tasks_data = []
for node in data['topology']['nodes']:
	name = node['name']
	port = node['console']
	path = f"configs/i{name[1:]}_startup-config.cfg" # Dossier où le script de génération a déposé les fichiers de config
	tasks_data.append((name, port, path))


async def deploiement_telnet(router_name, port, config_file):

    print(f"--- Connexion à {router_name} sur le port {port} ---")
    try:
        _, writer = await telnetlib3.open_connection(
            host="127.0.0.1",
            port=port,
            shell=None,
            connect_minwait=1.0, # On laisse le temps à la nego de se calmer
            connect_maxwait=1,
            encoding='utf-8',
            force_binary=False,
            term='vt100') # on force un terminal très simple ('vt100') pour limiter les échanges IAC
             
        writer.write('\x03') # Equivalent à un Ctrl+C
        writer.write('\r\n\r\n\r\n') # Simule la touche "Entrée" 3 fois pour réveiller la console
        writer.write('no\r\n')
        await writer.drain()
        await asyncio.sleep(2) # il peut y avoir beaucoup de blabla après le no
        writer.write('\x03') # On recoupe direct au cas où le 'no' a lancé une recherche DNS (s'il n'y a pas eu la demande yes/no)
        await writer.drain() # FORCE l'envoi des données du buffer vers le réseau

        writer.write("enable\r\n") # Passage en enable
        await writer.drain()
        await asyncio.sleep(0.5)
        writer.write("conf t\r\n") # Passage en mode configuration
        writer.write("no ip domain-lookup\r\n") # évite les pb en cas de mauvaise entrée
        await writer.drain()

        # Lecture du fichier .cfg généré et envoi ligne par ligne
        with open(config_file, 'r', encoding='utf-8') as f:
            for line in f:
                clean_line = line.strip() # On enlève les espaces et sauts de ligne invisibles
                if clean_line: # On n'envoie que si la ligne n'est pas vide
                    writer.write(clean_line + "\r\n")
                    await writer.drain()
                    await asyncio.sleep(0.1) # Délai pour ne pas saturer le buffer du routeur


                
        # Sauvegarde et fin
        writer.write("end\r\n")
        writer.write("write memory\r\n\r\n") # double \r\n pour la confirmation
        writer.write("exit\r\n")
        await writer.drain()
        await asyncio.sleep(2)

        writer.close()
        #print(f"Configuration de {router_name} terminée via Telnet")
        return f"{router_name} OK"

    except Exception as e:
        print(f"Erreur sur {router_name}: {e}")
        return f"{router_name} ERROR"



async def main():

    # lance génération conf
    print("Début de la génération des fichiers de configuration")
    generate_main(INTENT_FILE)
    
   
    # On crée une liste de tâches (coroutines)
    tasks = [deploiement_telnet(name, port, path) for name, port, path in tasks_data]
    
    print(f"Lancement du déploiement des routeurs")
    # .gather lance TOUT en même temps et attend que tout soit fini
    results = await asyncio.gather(*tasks)
    
    print("\n--- Génération et Déploiement terminé ---")
    for res in results:
        print(res)

if __name__ == "__main__":
    asyncio.run(main())

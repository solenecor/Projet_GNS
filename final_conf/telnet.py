import json
import telnetlib3
import asyncio

# importation du code pour générer les configs
from generate_conf import main as generate_main 

INTENT_FILE = "intent_file_17_routers.json"
GNS3_FILE = '17_routers.gns3'
route_reflection = False

# charge le fichier gns3
with open(GNS3_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f) 
    
tasks_data = [] # liste pour stocker les données utiles
for node in data['topology']['nodes']: # le fichiers gns3 est sous la forme de liste de liste de noeuds
	name = node['name'] # on récupère le nom,
	port = node['console'] # le port associé
	path = f"configs/i{name[1:]}_startup-config.cfg" # Chemin vers où le script de génération a déposé les fichiers de config
	tasks_data.append((name, port, path))


async def deploiement_telnet(router_name, port, config_file):

    print(f"--- Connexion à {router_name} sur le port {port} ---")
    try:
        reader, writer = await telnetlib3.open_connection(
            host="127.0.0.1",
            port=port,
            shell=None, #
            connect_minwait=1.0, # 
            connect_maxwait=1, #
            encoding=None,  # 
            force_binary=True, # 
            )

        writer.write(b'no\r\n') # pour répondre à la quetsion "Would you like to enter the initial configuration dialog? [yes/no]:" qui peut apparaître au début
        await writer.drain()
        await asyncio.sleep(0.5)
        
        writer.write(b"enable\r\n") # Passage en enable
        await writer.drain()
        await asyncio.sleep(0.1) # pour etre sur 
        writer.write(b"conf t\r\n") # Passage en mode configuration
        writer.write(b"no ip domain-lookup\r\n") # évite les pb en cas de mauvaise entrée
        await writer.drain()
        await asyncio.sleep(0.1)

        # Lecture du fichier .cfg généré et envoi ligne par ligne
        with open(config_file, 'r') as f:
            for line in f:
                clean_line = line.strip() # On enlève les espaces et sauts de ligne invisibles
                if clean_line: # On envoie que si la ligne n'est pas vide
                    writer.write(clean_line.encode() + b"\r\n") # on oublie pas de simuler la touche entrée
                    await writer.drain()
                    await asyncio.sleep(0.1) # Délai pour ne pas saturer le buffer du routeur


                
        # Sauvegarde et fin
        writer.write(b"write memory\r\n\r\n") # double \r\n pour la confirmation
        writer.write(b"exit\r\n")
        await writer.drain()
        writer.close()
        await asyncio.sleep(5) # le temps que tout arrive bien au routeur

        return f"{router_name} OK"

    except Exception as e:
        print(f"Erreur sur {router_name}: {e}")
        return f"{router_name} ERROR"



async def main():

    # lance génération des configs
    print("Début de la génération des fichiers de configuration")
    generate_main(INTENT_FILE, route_reflection)
    
   
    # On crée une liste de tâches, 1 par routeur
    tasks = [deploiement_telnet(name, port, path) for name, port, path in tasks_data]
    
    print(f"Lancement du déploiement des routeurs")
    # .gather lance tout en même temps et attend que tout soit fini 
    results = await asyncio.gather(*tasks)
    
    
    for res in results:
        print(res)

    print("\n--- Génération et Déploiement terminé ---")

if __name__ == "__main__":
    asyncio.run(main())

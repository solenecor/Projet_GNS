import json
import telnetlib3
import time
import asyncio
from multiprocessing import Pool

# Récupération des noms des dossiers où les configs doivent être placées
# A MODIFIER : nom du fichier gns3
with open('automatisation_telnet.gns3', 'r', encoding='utf-8') as f:
    data = json.load(f)
    
tasks_data = []
for node in data['topology']['nodes']:
	name = node['name']
	port = node['console']
	path = f"configs2/i{name[1:]}_startup-config.cfg" # Dossier où le script de génération a déposé les fichiers de config
	tasks_data.append((name, port, path))

def wrapper(args):
    """
    Un wrapper est nécessaire car Pool.map ne prend qu'un seul argument.
    On décompresse le tuple (name, port, config_file).
	Exécute la boucle asynchrone pour UN routeur dans UN processus du pool
	"""
    return asyncio.run(deploiement_telnet(*args))

async def deploiement_telnet(router_name, port, config_file):
    print(f"--- Connexion à {router_name} sur le port {port} ---")
    try:
        _, writer = await telnetlib3.open_connection(
            host="127.0.0.1",
            port=port,
            shell=None,
            connect_minwait=0.5,
            connect_maxwait=1,
            encoding=None,
            force_binary=True)
        writer.write(b'\r\n') # Simule la touche "Entrée" pour réveiller la console
        await writer.drain() # FORCE l'envoi des données du buffer vers le réseau
        await asyncio.sleep(1)  # Attente d'une seconde pour que le routeur réponde


        writer.write(b"conf t\r\n") # Passage en mode configuration
        await writer.drain()

        # Lecture du fichier .cfg généré et envoi ligne par ligne
        with open(config_file, 'rb') as f:
            for line in f:
                writer.write(line + b"\r\n")
                await writer.drain() 
                await asyncio.sleep(0.1) #  Délai pour ne pas saturer le buffer du routeur

                
        # Sauvegarde et fin
        writer.write(b"end\r\n")
        writer.write(b"write memory\r\n\r\n") # double \r\n pour la confirmation
        writer.write(b"exit\r\n")
        await writer.drain()
        await asyncio.sleep(1)

        writer.close()
        #print(f"Configuration de {router_name} terminée via Telnet")
        return f"{router_name} OK"

    except Exception as e:
        print(f"Erreur sur {router_name}: {e}")
        return f"{router_name} ERROR"

		
if __name__ == "__main__":
	
	with Pool(processes=20) as pool:
		print("Lancement du déploiement")
		results = pool.map(wrapper, tasks_data)
	print("Déploiement terminé.")
	for res in results:
		print(res)

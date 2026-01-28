import json
import os
import shutil

# importation du code pour générer les configs
from generate_conf import main as generate_main 

INTENT_FILE = "intent_file_17_routers.json"
GNS3_FILE = '17_routers.gns3'
SOURCE_CFG_DIR = "configs"
GNS3_PROJECT_ROOT = "" # a compléter si le script est pas à la racine du projet GNS3
route_reflection = False


def run_drag_and_drop_bot():
    # lance génération des configs
    print("Début de la génération des fichiers de configuration")
    generate_main(INTENT_FILE, route_reflection)
    
    # déploiement  
    if not os.path.exists(GNS3_FILE): # Vérifie existence projet_GNS3.gns3
        print(f"Erreur : Le fichier {GNS3_FILE} est introuvable.")
        return 

    # charge fichier gns3
    with open(GNS3_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # dictionnaire vide pour stocker les ID routeurs 
    folders = {}
    
    for node in data['topology']['nodes']: #parcours liste de noeuds 
        name = node['name']       # récupère le nom du routeur 
        node_id = node['node_id'] # récupère l'UUID unique (ex: "550e8400-e29b...")
        folders[name] = node_id   # remplit dico

    # pour chaque routeur
    for name, node_id in folders.items():
        source_file = os.path.join(SOURCE_CFG_DIR, f"i{name[1:]}_startup-config.cfg") # Reconstruit le chemin du fichier source généré

        if os.path.exists(source_file): # vérifie si les fichiers sont déjà présents 
            # construit le chemin destination spécifique à GNS3/Dynamips
            target_path = os.path.join(
                GNS3_PROJECT_ROOT, 
                "project-files", 
                "dynamips", 
                node_id, 
                "configs", 
                f"i{name[1:]}_startup-config.cfg"
            )

            try:
                # crée dossiers destination s'ils n'existent pas 
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                
                # copie fichier source vers l'emplacement interne de GNS3
                shutil.copy(source_file, target_path)
                print(f" {name} : Config copiée vers {node_id}") 
            except Exception as e:
                # capture toute erreur
                print(f" Erreur pour {name} ({node_id}) : {e}")
        else:
            # alerte que le routeur n'a pas de fichier .cfg correspondant
            print(f" Fichier introuvable pour {name} ({source_file})")

if __name__ == "__main__":
    run_drag_and_drop_bot()
    print("\n[Terminé] Génération et Déploiement réussis.")

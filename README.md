# Projet de programmation réseau - utilisation de GNS3
Pour ce projet, nous avons créé différentes configurations: *

## Configurations 
### **Configuration à 6 routeurs** ```conf_manuelle```

Cette configuration a été réalisée à la main pendant les 4 premières heures de projet et nous a permis de vérifier les résultats obtenus par nos premiers essais d'intent file, d'automatisation python et de drag and drop.

Elle contient également des **bgp policies** (impliquant la création de *route-maps*) pour vérifier le bon fonctionnement de notre fichier d'automatisation python.

### **Configuration à 17 routeurs** ```final_conf```

 ![Configuration à 17 routeurs et connexion avec d'autres AS](img/final_config.png)

Description de la configuration: 
- AS1: {R1, R2, R3, R4, R5, R6, R7} ; RIP ; qui a le rôle de peer
- AS2: {R7, R8, R9, R10, R11, R12, R13, R14}; OSPF ; qui a le rôle de peer
- AS3: {R15}; RIP ; qui a le rôle de provider
- AS4: {R16}; RIP ; qui a le rôle de customer
- AS5: {R17}; RIP ; qui a le rôle de customer

Cette configuration est la version finale de notre code comprenant les améliorations suivantes: 
- Les BGP Policies
- Les Router Reflector
- Les coûts OSPF
- Le déploiement Telnet

## Fonctionnement
Avant tout, il faut posséder le fichier `.gns3` avec la configuration souhaitée, ainsi que le fichier `.json` qui contient l'intent file formaté correctement. 
> Attention : les interfaces précisées dans l'intent file doivent être strictement les mêmes que celles configurées dans GNS3. 
### Drag and drop bot
Le fichier `drag_and_drop_bot.py` contient les variables `INTENT_FILE` `.gns3` et `.json`. 
### Telnet

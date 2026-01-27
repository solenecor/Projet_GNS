# Projet de programmation réseau - utilisation de GNS3
Pour ce projet, nous avons créé différentes configurations:

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

---

## Utilisation

Avant de commencer, assurez-vous de disposer des éléments suivants :

- Un fichier **`.gns3`** correspondant au projet GNS3 avec la topologie et les équipements configurés.
- Un fichier **`.json`** (intent file) correctement formaté, décrivant les intentions de configuration.
- Les scripts Python suivants, placés dans un même répertoire :
  - `drag_and_drop_bot.py`
  - `telnet.py`
  - `generate_conf.py`

> **Attention**  
> Les interfaces spécifiées dans l’*intent file* doivent correspondre strictement aux interfaces configurées dans GNS3 (noms, numérotation, etc.). Toute incohérence empêchera l’application correcte des configurations.
> 
> Aussi, il existe une fonction Route reflector, pour l'activer, rendez-vous dans les fichiers python `drag_and_drop_bot.py` ou `telnet.py` et passez la variable **route_reflector** à `True`.
>

### Drag and Drop Bot

Le script `drag_and_drop_bot.py` repose sur trois variables principales :

- `INTENT_FILE` : nom du fichier `.json` contenant l’intent.
- `GNS3_FILE` : nom du fichier `.gns3` du projet.
- `GNS3_PROJECT_ROOT` : chemin vers la racine du projet GNS3 (uniquement nécessaire si le script n’est pas placé à la racine).

**Recommandation** : placer l’ensemble des fichiers (`.gns3`, `.json` et scripts Python) directement à la racine du projet GNS3 afin d’éviter toute erreur de chemin.

Une fois les variables correctement renseignées, lancez le script : `drag_and_drop_bot.py`

Le script est `./` friendly avec le `#!/usr/bin/env python3` donc vous pouvez le lancer avec la commande `python 3 drag_and_drop_bot.py` mais aussi avec `./drag_and_drop_bot.py` (attention, si vous êtes sur windows il faudra juste faire un `dos2unix *` (ou `dos2unix drag_and_drop_bot.py`) pour supprimer les retours chariots entre autres !!)

Ce script :
- génère automatiquement les fichiers de configuration adaptés à chaque routeur ;
- dépose ces configurations dans les répertoires appropriés du projet GNS3.

> Note importante :
> 
> Les routeurs doivent être éteints lors de l’exécution du script.
> Une fois le script terminé, démarrez les routeurs : les configurations seront alors chargées automatiquement au démarrage.
>

### Telnet

Le script `telnet.py` fonctionne selon le même principe de configuration préalable :
- renseigner correctement les noms des fichiers (`.json`, `.gns3`) ;
- définir le chemin vers la racine du projet GNS3 si nécessaire.

Lancez ensuite le script : `telnet.py`

> Note importante :
> 
> Les routeurs doivent impérativement être démarrés (liens actifs en vert dans GNS3), car le script se connecte directement à chaque équipement via Telnet.

---

## Tests de fonctionnement

### Vérifier les interfaces et adresses IPv6


```bash
show ipv6 interface brief

```

**vérifié si:** Toutes les interfaces sont **"up/up"** avec les bonnes **adresses IPv6** (loopback et liens)

###  Vérifier RIPng (AS1)


```bash
show ipv6 rip [AS1] database
show ipv6 route rip

```

**vérifié si:**  il y a ripng dans la database de l'AS1, AS3, AS4 et AS5 et des routes avec le code `R` après avoir affiché les routes.

### Vérifier OSPFv3 (AS2)


```bash
show ipv6 ospf neighbor
show ipv6 ospf interface
show ipv6 route ospf

```

**vérifié si:**  il y a des voisins OSPF en état `FULL/DR`, `FULL/BDR` , les **coûts OSPF** corrects au réseau (dans notre réseau, on a mis 10 ou 100), des routes avec le code `O` dans `show ipv6 route`

### Vérifier costs OSPFv3 (AS2)

```
traceroute <ipv6>
```

**vérifié si:**  de R14 à R12 (ospf_cost = 100), le chemin passe bien par R13, et pas directement sur le lien. 
### Vérifier les sessions BGP (R7, R9)

```bash
show bgp ipv6 unicast summary

```

**vérifié si:**  il y a des voisins BGP listés, le **state** à `Established` et des **routes reçues** entre les AS, pour vérifier les routes BGP, `show bgp ipv6 unicast`, il faut appercevoir les préfixes BGP reçus et le **next-hop**, **AS_PATH**, **LocPrf**
 

### Vérifier les communities BGP

```bash
show bgp ipv6 unicast neighbors <ip> received-routes
show bgp ipv6 unicast neighbors <ip> advertised-routes

```

avec `| include Community` pour filtrer :

```bash
show bgp ipv6 unicast neighbors <ip> received-routes | include Community

```

**vérifié si:**  il y a des **communities** ( `1:10`, `2:20`) (ou leur version décimale : - `1:100` = 1 * 65536+10=65546
- `1:20` = 1 * 65536+20=65556) et les routes taggées

ou simplement : 
```
sh ipv6 route
```
**vérifié si:** Par exemple AS3 n'a pas de route vers AS2, et inversement

### Vérifier les route-maps et community-lists

```bash
show run | section route-map
show run | include community-list

```

**vérifié si:**  il y a les `route-map SET-COMMUNITY-...`, `SET-LOCALPREF-...`, `EXPORT-FILTER-...` et les `ip community-list` avec les bons IDs


### Vérifier les routes exportées

```bash
show bgp ipv6 unicast neighbors <ipv6> advertised-routes

```

**vérifié si:**  seules les routes autorisées par `EXPORT-FILTER` sont envoyées et les bonnes communities sont présentes

### Vérifier la connectivité entre 2 routeurs 


```bash
ping ipv6 <loopback_router_1>
traceroute ipv6 <loopback_router2>

```

**vérifié si:**  le ping réussit et le traceroute suit le **chemin OSPF avec les bons coûts**



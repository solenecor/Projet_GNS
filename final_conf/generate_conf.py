#!/usr/bin/env python3

### bonne version 


import json
import ipaddress
from dataclasses import dataclass, field
import os
import shutil 
from typing import Dict, List, Optional

## @ : alias --> permet de créer une fonction init sans avoir à la déf : + rapide

@dataclass
class Interface:
    name: str
    ipv6: ipaddress.IPv6Address
    prefix_len: int
    ospf_area: Optional[int] = None # area ospf
    ripng: bool = False # does rip?


@dataclass
class Neighbor:
    router: str
    type: str
    interface: str
    ospf_cost: Optional[int]= None # cout ospf, attribut optionnel de type int, si non renseigné, alors vaut None
    bgp_role: Optional[str] = None   # provider, customer ou peer


@dataclass
class Router:
    name: str
    role: str ## is it a core router or orborder router ?
    asn: int
    neighbors: List[Neighbor]
    rr_role: str = "client" # par défaut, si rien renseigné, on dir que c pas un reflection router.
    rr_role: str = "client" # par défaut, si rien renseigné, on dir que c pas un reflection router.
    loopback: Optional[ipaddress.IPv6Address] = None
    interfaces: Dict[str, Interface] = field(default_factory=dict)
    bgp_neighbors: Dict[str, int] = field(default_factory=dict)
    bgp_policies: Dict[str, Dict[str, str]] = field(default_factory=dict)

## la structure : interfaces: Dict[str, Interface] = field(default_factory=dict)
# interface est un dictionnaire avec des clés de type str et des valeurs de type interface, 
# field : personalise le comportement de l'atribue. ici : par défaut (si l'user ne donne pas de dict), on mettra un dict vide.



@dataclass
class AutonomousSystem:
    name: str
    asn: int
    ipv6_prefix: ipaddress.IPv6Network
    loopback_pool: ipaddress.IPv6Network
    link_pool: ipaddress.IPv6Network
    inter_as_link_pool: ipaddress.IPv6Network
    protocol: str
    process_id: Optional[int] = None
    area: Optional[int] = None
    routers: Dict[str, Router] = field(default_factory=dict)
    bgp_policies: Dict[str, Dict] = field(default_factory=dict) ###

    def allocate_loopback(self) -> ipaddress.IPv6Address:
        """allocates loopback addresses for routers who need one"""
        used = {r.loopback for r in self.routers.values() if r.loopback} ## r : short for router
        for ip in self.loopback_pool.hosts():
            if ip not in used:
                return ip
        raise ValueError("Loopback pool exhausted")

    def allocate_link_prefix(self, inter_as: bool = False) -> ipaddress.IPv6Network:
        """
        Alloue le prochain sous-réseau /64 disponible pour un lien réseau.
        
        Fonctionnement : Parcourt la plage d'adresses pool (intra-AS ou inter-AS) et retourne le premier 
        préfixe qui n'est pas encore utilisé par une interface de l'AS.

        Paramètres :
            inter_as (bool): vérifier s'il faut prendre dans la plage inter as ou l'autre plage

        Return:
            ipaddress.IPv6Network: Un objet réseau représentant le préfixe /64 alloué.
        """
        pool = self.inter_as_link_pool if inter_as else self.link_pool ## pool : plage d'adresses
        subnets = list(pool.subnets(new_prefix=64))

        used = set()
        for r in self.routers.values():
            for iface in r.interfaces.values():
                net = ipaddress.IPv6Network(f"{iface.ipv6}/{iface.prefix_len}", strict=False) ## creation d'un network, strict = False : qu'on donne une adresse hote (qqch::1/64) ou un reseau (qqch::/64), python comprend qu'on parle d'un réseau.
                used.add(net.supernet(new_prefix=64)) ## pour pas ré alouer

        for net in subnets:
            if net not in used:
                return net
        raise ValueError("Link pool exhausted") ## si n'arrive pas à trouver une adresse (car plus de place par ex), raise renvoie un msg d'erreur




def parse_intent(path: str) -> Dict[str, AutonomousSystem]:
    """
        Analyse le fichier d'intention JSON et construit la topologie réseau logique : charge les données JSON pour créer les instances de classes 
        AutonomousSystem, Router et Neighbor (interfaces, protocoles IGP, pools IP) et identifie les relations inter-AS (provider, peer, 
       customer) pour assigner les rôles BGP et les politiques de filtrage (communautés, local-pref) aux routeurs de bordure.

    Paramètres:
        path (str): Chemin vers le fichier JSON contenant l'intent.

    Return:
        as_map : Dict[str, AutonomousSystem]: Un dictionnaire associant les noms d'AS à leurs objets respectifs.
    
    Note:
        La fonction utilise un dictionnaire inversé (as_roles) pour mapper les ASN 
        distants aux rôles définis dans les politiques BGP locales.
    """
    data = json.load(open(path)) # open ouvre juste le fichier, c'est load qui le comprend et le convertit en obj python
    as_map: Dict[str, AutonomousSystem] = {}

    # Création des objets AutonomousSystem et Router
    for as_data in data["autonomous_systems"]:
        as_obj = AutonomousSystem(
            name=as_data["name"],
            asn=as_data["asn"],
            ipv6_prefix=ipaddress.IPv6Network(as_data["addressing"]["ipv6_prefix"]),
            loopback_pool=ipaddress.IPv6Network(as_data["addressing"]["loopback_pool"]),
            link_pool=ipaddress.IPv6Network(as_data["addressing"]["link_pool"]),
            inter_as_link_pool=ipaddress.IPv6Network(data["bgp"]["inter_as_link_pool"]),
            protocol=as_data["routing"]["protocol"],
            process_id=as_data["routing"].get("process_id"),
            area=as_data["routing"].get("area"),
            bgp_policies = as_data.get("bgp_policies", {})
        )
        ## création des obj Router
        for rdata in as_data["routers"]:
            router = Router(
                name=rdata["name"],
                role=rdata["role"],
                asn=as_obj.asn,
                rr_role=rdata.get("rr_role", "client"), # <-- Si absent du JSON, rr_role vaudra "client"
                neighbors=[Neighbor(**n) for n in rdata.get("neighbors", [])] ## transforme une liste de dictionnaires JSON en une liste d'objets Neighbor. Neighbor(**n) : associe chaque clé du dictionnaire à l'argument correspondant dans la classe Neighbor.
            )
            as_obj.routers[router.name] = router
        as_map[as_obj.name] = as_obj

    # Appliquer les politiques BGP selon les relations inter-AS
    for as_data in data["autonomous_systems"]:
        local_asn = as_data["asn"]
        local_as_name = as_data["name"]
        bgp_policies = as_data.get("bgp_policies", {})
        neighbors = bgp_policies.get("as_neighbors", {})
        policies = bgp_policies.get("policies", {})

        # Inverser la table pour retrouver le rôle d’un ASN : voir la note dans la docstring
        as_roles = {}
        for role, remote_as_list in neighbors.items():
            if role not in ("provider", "peer", "customer"):
                continue
            for remote_as in remote_as_list:
                as_roles[int(remote_as)] = role

        for router_data in as_data["routers"]:
            router = as_map[local_as_name].routers[router_data["name"]]
            for neigh in router.neighbors:
                if neigh.type == "inter-as":
                    remote_as_name, remote_router_name = neigh.router.split(":")
                    remote_asn = as_map[remote_as_name].asn
                    role = as_roles.get(remote_asn)

                    if not role:
                        continue  # pas de rôle défini -> pas de policy
                    
                    neigh.bgp_role = role
                    policy = {}
                    ## prépare les policies ici et les écrit dans generate_router_config
                    if role in policies.get("communities", {}):
                        policy["set_community"] = policies["communities"][role] 
                    if role in policies.get("local_pref", {}):
                        policy["local_pref"] = policies["local_pref"][role]
                    if role == "provider":
                        policy["export_only_community"] = policies["communities"]["provider"]

                    router.bgp_policies[remote_router_name] = policy
                    role = as_roles.get(remote_asn)
                    if role:
                        neigh.bgp_role = role

    return as_map


def allocate_addresses(as_map: Dict[str, AutonomousSystem]) -> None:
    """
    attribution globale des adresses IPv6 sur le réseau. (loopbacks et liens physiques), gère également l'activation des protocoles IGP (OSPFv3 ou RIPng) sur 
    chaque interface en fonction de la configuration de l'AS.

    paramètres :
        as_map (Dict[str, AutonomousSystem]): Un dictionnaire associant les noms d'AS à leurs objets respectifs, créé dans parse_intent

    pas de return 

    Note:
        L'attribution des liens est bidirectionnelle : lorsqu'un routeur configure 
        son côté du lien, il configure simultanément l'interface correspondante 
        chez son voisin pour éviter les doubles allocations.
    """
    # Loopback allocation
    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            router.loopback = as_obj.allocate_loopback()

    # Intra-AS links allocation
    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            for neigh in router.neighbors:
                if neigh.type == "intra-as":
                    neigh_router = as_obj.routers[neigh.router] ## permet de retrouver l'autre routeur
                    if neigh.interface not in router.interfaces: ## bidirection et vérification de non-répétition
                        link_prefix = as_obj.allocate_link_prefix(inter_as=False)
                        r_ip = link_prefix[1]
                        n_ip = link_prefix[2]

                        router.interfaces[neigh.interface] = Interface(
                            name=neigh.interface,
                            ipv6=r_ip,
                            prefix_len=64,
                            ospf_area=as_obj.area if as_obj.protocol == "ospfv3" else None,
                            ripng=(as_obj.protocol == "rip")
                        )

                        remote_iface = next(n.interface for n in neigh_router.neighbors if n.router == router.name)
                        neigh_router.interfaces[remote_iface] = Interface(
                            name=remote_iface,
                            ipv6=n_ip,
                            prefix_len=64,
                            ospf_area=as_obj.area if as_obj.protocol == "ospfv3" else None,
                            ripng=(as_obj.protocol == "rip")
                        )


def build_bgp_fullmesh(as_map: Dict[str, AutonomousSystem]) -> None:
    """
    Établit une topologie iBGP full-mesh pour chaque système autonome.

    Cette fonction parcourt tous les systèmes autonomes (AS) et connecte les routeurs du même AS
    via Loopback @. --> chaque routeur établit une session iBGP directe avec tous ses pairs internes dpc pas de pb propagation des routes eBGP dans l'AS.

    Paramètres :
        as_map (Dict[str, AutonomousSystem]): Un dictionnaire associant les noms d'AS à leurs objets respectifs, créé dans parse_intent

    Return:
        None car routers directement modif.
    """
    for as_obj in as_map.values():
        routers = list(as_obj.routers.values())
        for i in range(len(routers)):
            for j in range(i + 1, len(routers)): ## parc routeurs *2 
                r1, r2 = routers[i], routers[j]
                r1.bgp_neighbors[str(r2.loopback)] = as_obj.asn ## loopback
                r2.bgp_neighbors[str(r1.loopback)] = as_obj.asn

def build_bgp_rr(as_map: Dict[str, AutonomousSystem]) -> None:
    """
    Établit une topologie iBGP basée sur le Route Reflection pour chaque système autonome.
    - Les RR-Clients ne font de sessions qu'avec les RR-Servers.
    - Les RR-Servers font des sessions avec TOUS les autres routeurs (Full-mesh entre Servers + Clients).

    Paramètres :
        as_map (Dict[str, AutonomousSystem]): Un dictionnaire associant les noms d'AS à leurs objets respectifs, créé dans parse_intent

    Return:
        None car routers directement modif.
    """
    for as_obj in as_map.values():
        routers = list(as_obj.routers.values())
        
        # On identifie les rôles (on utilise .get au cas où le champ est absent)
        for as_obj in as_map.values():
            routers = list(as_obj.routers.values())
            for i in range(len(routers)):
                for j in range(i + 1, len(routers)):
                    r1, r2 = routers[i], routers[j]
                
                # Règle de session iBGP RR :
                # On crée la session si au moins UN des deux est un serveur.
                if r1.rr_role == "server" or r2.rr_role == "server":
                    r1.bgp_neighbors[str(r2.loopback)] = as_obj.asn
                    r2.bgp_neighbors[str(r1.loopback)] = as_obj.asn

def build_inter_as_neighbors(as_map: Dict[str, AutonomousSystem], inter_as_iterator) -> None:
    """
    Pour toutes las iface inter as, création/ remplissage d'un iterateur GLOBAL stockant @ 
    ip pr éviter d'avoir plusieurs iface avec la même @ip. Alloue une @ ipv6/64 de sous-réseau et config des obj interface pour les 2 routeurs.

    Paramètres :
        as_map (Dict[str, AutonomousSystem]): Un dictionnaire associant les noms d'AS à leurs objets respectifs, créé dans parse_intent
        inter_as_iterator (iterator): Itérateur Python générant des sous-réseaux IPv6 

    Return :
        None: Les objets Router et Interface dans as_map sont modifiés par effet de bord.
    """
    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            for neigh in router.neighbors:
                if neigh.type == "inter-as":
                    remote_as_name, remote_router_name = neigh.router.split(":")
                    if remote_router_name > router.name:  # pour vérifier que chaque lien n'est traité qu'une suele fois.
                        remote_as = as_map[remote_as_name] 
                        remote_router = remote_as.routers[remote_router_name]

                        # On récupère un /64 unique depuis l'itérateur global
                        link_prefix = next(inter_as_iterator)

                        r_ip = link_prefix[1] # router
                        n_ip = link_prefix[2] # neighbor

                        router.interfaces[neigh.interface] = Interface(
                            name=neigh.interface,
                            ipv6=r_ip,
                            prefix_len=64,
                            ospf_area=as_obj.area if as_obj.protocol == "ospfv3" else None,
                            ripng=False
                        )
                        ## remote : désigne le voisin ( local : routeur sur lequel on est, remote; routeur au bout de la liaison avec le local)
                        remote_iface = next(n.interface for n in remote_router.neighbors if n.router == f"{as_obj.name}:{router.name}") # la prochaine interface voisine si on est dans mon router)
                        remote_router.interfaces[remote_iface] = Interface(
                            name=remote_iface,
                            ipv6=n_ip,
                            prefix_len=64,
                            ospf_area=remote_as.area if remote_as.protocol == "ospfv3" else None,
                            ripng=False
                        )

                        router.bgp_neighbors[str(n_ip)] = remote_as.asn
                        remote_router.bgp_neighbors[str(r_ip)] = as_obj.asn

def router_id_from_name(router_name: str) -> str:
    # R1 -> 1.1.1.1 
    num = int(router_name.lstrip("R")) # enlève le R de R1 et convertit en entier le 1
    return f"{num}.{num}.{num}.{num}"

def determine_bgp_role(local_asn, remote_asn, bgp_policies):
    '''
    Parcours la liste des voisin de local_asn et renvoie le role associé au voisin remote_asn (None si rien et rôle si voisin)
    '''
    for role, as_list in bgp_policies["as_neighbors"].items():
        if remote_asn in as_list:
            return role
    return None

def generate_router_config(router: Router, as_obj: AutonomousSystem, as_map: Dict[str, AutonomousSystem], reflection_routing = False) -> str:
    """
    Génère l'intégralité du fichier de configuration de démarrage (startup-config) pour un routeur Cisco, avec les paramètres systèmes, interfaces, 
    voisinage, BGP, RIP, OSPF, Communities et route-map.

    Paramètres :
        router (Router): L'objet routeur à configurer, avec ses interfaces et voisins.
        as_obj (AutonomousSystem): Le système autonome auquel appartient le routeur.
        as_map (Dict[str, AutonomousSystem]): La cartographie globale du réseau pour résoudre 
            les relations inter-AS.

    Return:
        str: Une chaîne de caractères contenant l'intégralité des commandes Cisco IOS 
             prêtes à être écrites dans un fichier .cfg.
    """
    rid = router_id_from_name(router.name)

    # Find inter-AS interface (if any)
    inter_as_iface = None
    for neigh in router.neighbors:
        if neigh.type == "inter-as":
            inter_as_iface = neigh.interface
            break
    
    # si ospf : remplissage des ospf_cost 
    iface_costs = { n.interface: n.ospf_cost for n in router.neighbors if n.ospf_cost is not None and n.type == "intra-as" } # crée un dico avec les couts ospf par interface 

    
    bgp_role_by_ip = {} # dico des rôles bgp, puis remplissage :

    for neigh in router.neighbors:
        if neigh.type == "inter-as":
            # IP locale
            local_ip = router.interfaces[neigh.interface].ipv6

            # Trouver le router distant
            remote_as_name, remote_router_name = neigh.router.split(":")

            remote_as = as_map[remote_as_name]
            remote_router = remote_as.routers[remote_router_name]

            # Trouver l'interface du voisin qui pointe vers nous
            remote_iface_name = next( n.interface for n in remote_router.neighbors if n.router == f"{as_obj.name}:{router.name}") # prochaine interface voisine 

            remote_ip = remote_router.interfaces[remote_iface_name].ipv6 ## .ipv6 : attribut @ ipv6 de la classe interface

            # Mapping IP du voisin -> rôle
            bgp_role_by_ip[str(remote_ip)] = neigh.bgp_role
    #print(bgp_role_by_ip)

    lines = []
    lines.append("!")
    lines.append("version 15.2") # version
    lines.append("service timestamps debug datetime msec") # timestamp pour les msg de debugage je crois
    lines.append("service timestamps log datetime msec") # timestamp pour les msg de system / de console (log)
    lines.append("!")
    lines.append(f"hostname {router.name}")
    lines.append("!")
    lines.append("boot-start-marker") # flag de début de la zone contenant les commandes de démarrage 
    lines.append("boot-end-marker") # flag de fin de la zone.
    lines.append("!")
    lines.append("no aaa new-model") # Ne pas activer le nouveau modèle de sécurité AAA (Authentication, Authorization, and Accounting) qui permet de gérer les accès au routeur avec des droits et tout.
    lines.append("no ip icmp rate-limit unreachable") 
    lines.append("ip cef") # CEF : Cisco Express Forwarding : permet de simplifier table route / fwd pour router paquets quasi instantanément
    lines.append("!")
    lines.append("no ip domain lookup") # je crois que en gros si erreur on recherche pas l'erreur sur internet mais on affiche msg d'erreur ? 
    lines.append("ipv6 unicast-routing")
    lines.append("ipv6 cef")
    lines.append("!")
    lines.append("multilink bundle-name authenticated") # si deux lien du même départ menant au même endroit : regroupe les deux liens
    lines.append("!")
    lines.append("ip tcp synwait-time 5") # si envoi connexion tcp que 5 sec à l'autre côté pour répondre 
    lines.append("!")
    lines.append("interface Loopback0")
    lines.append(" no ip address")
    lines.append(" no shutdown")
    lines.append(f" ipv6 address {router.loopback}/128")
    lines.append(" ipv6 enable")
    if as_obj.protocol == "ospfv3":
        lines.append(f" ipv6 ospf {as_obj.process_id} area {as_obj.area}") #
    elif as_obj.protocol == "rip": 
        lines.append(f" ipv6 rip {as_obj.name} enable") 
    lines.append("!")

    for iface in router.interfaces.values():
        lines.append(f"interface {iface.name}")
        lines.append(" no ip address")
        lines.append(" no shutdown")
        lines.append(" negotiation auto") # débit de données envoyer : en prenant le + petit débit 
        lines.append(f" ipv6 address {iface.ipv6}/{iface.prefix_len}")
        lines.append(" ipv6 enable")

        if as_obj.protocol == "ospfv3":
            lines.append(f" ipv6 ospf {as_obj.process_id} area {iface.ospf_area}") #
            if iface.name in iface_costs: #
                lines.append(f" ipv6 ospf cost {iface_costs[iface.name]}") #

        if iface.ripng:
            lines.append(f" ipv6 rip {as_obj.name} enable")

        lines.append("!")

    
    # BGP
    lines.append(f"router bgp {router.asn}")
    lines.append(f" bgp router-id {rid}") #rid : router id 
    lines.append(" bgp log-neighbor-changes") # permet au router d'alerter si y a des changements de states dans ses bgp sessions
    if router.role == "border":
        lines.append(" no synchronization")
        # no sync pour les border : c ok de partager les routes internes ici car on est en full mesh ? je suis pas sûre
    lines.append(" no bgp default ipv4-unicast")

    for neigh_ip, neigh_asn in router.bgp_neighbors.items():
        lines.append(f" neighbor {neigh_ip} remote-as {neigh_asn}")
        if neigh_asn == router.asn:
            lines.append(f" neighbor {neigh_ip} update-source Loopback0") # on n'ajoute cette ligne que pour notre as
            if reflection_routing and router.rr_role == "server":
                lines.append(f"  neighbor {neigh_ip} route-reflector-client")
    
    lines.append(" !")
    lines.append(" address-family ipv4") ## nécessaire ? je suis pas sure 
    lines.append(" exit-address-family")
    lines.append(" !")
    lines.append(" address-family ipv6")

    if router.role == "border":
        lines.append(f"  network {as_obj.ipv6_prefix}")
        if reflection_routing and router.rr_role == "server" and neigh_asn == router.asn:
            lines.append(f"  neighbor {neigh_ip} route-reflector-client")


    for neigh_ip in router.bgp_neighbors.keys():
        role = bgp_role_by_ip.get(neigh_ip)

        lines.append(f"  neighbor {neigh_ip} activate")
        if router.bgp_neighbors[neigh_ip] == router.asn:
            lines.append(f"  neighbor {neigh_ip} next-hop-self")
            lines.append(f"  neighbor {neigh_ip} send-community")


        # Appliquer la policy selon le rôle (provider/peer/customer)
        if role:
            if role in as_obj.bgp_policies["policies"].get("communities", {}):
                lines.append(f"  neighbor {neigh_ip} route-map SET-COMMUNITY-{role.upper()} in")
                
            if role == "customer":
                # On envoie TOUT au client (Internet, nos routes, etc.)
                lines.append(f"  neighbor {neigh_ip} route-map PASS-ALL out")

            elif role in ["provider", "peer"]:
                # On applique tes filtres de sécurité Gao-Rexford
                lines.append(f"  neighbor {neigh_ip} route-map EXPORT-FILTER-{role.upper()} out")
    lines.append(" exit-address-family")
    lines.append("!")

    # Rôles BGP réellement présents sur ce routeur
    roles_present = set()
    for neigh in router.neighbors:
        if neigh.type == "inter-as" and neigh.bgp_role:
            roles_present.add(neigh.bgp_role)

    # --- community-lists ---
    if router.role == "border": # il faut d├®finir les communaut├®s 
                                # sur tous les routeurs de bordure, m├¬me s'ils n'ont
                                #  pas de voisin direct comme ├ºa (par exemple, ils peuvent
                                #  avoir besoin d'appliquer une route map sur cette community, 
                                # m├¬me sans avoir de voisin de ce type)
        for role in ["peer","customer","provider"]:
            comm = as_obj.bgp_policies["policies"]["communities"][role]
            lines.append(f"ip community-list standard ONLY-{role.upper()} permit {comm}")
        lines.append("!")

    # --- route-maps set community + local-pref ---
    for role in roles_present:
        comm = as_obj.bgp_policies["policies"]["communities"][role]
        lp = as_obj.bgp_policies["policies"]["local_pref"][role]

        lines.append(f"route-map SET-COMMUNITY-{role.upper()} permit 10")
        lines.append(f" set community {comm}")
        lines.append(f" set local-preference {lp}")
        lines.append("!")


    # export filter (seulement si provider ou peer dans les voisins)    
    for role in ["provider","peer"]:
        if role in roles_present:
            lines.append(f"route-map EXPORT-FILTER-{role.upper()} deny 10")
            lines.append(" match community ONLY-PEER")
            lines.append(f"route-map EXPORT-FILTER-{role.upper()} deny 20")
            lines.append(" match community ONLY-PROVIDER")
            lines.append(f"route-map EXPORT-FILTER-{role.upper()} permit 30")
            lines.append("!")
    if "customer" in roles_present:
        lines.append("route-map PASS-ALL permit 10")
        lines.append("!")
    lines.append("ip forward-protocol nd") # autorise le protocol à fwd des neighbor discoveries
    lines.append("!")
    lines.append("no ip http server") #1.
    lines.append("no ip http secure-server") # 2. (1 et 2) -> désactiver l'interface web du router
    lines.append("!")

    # Route statique vers le supernet (pour les routeurs border) supernet : bloc d'adresses IPv6 global attribué à l'AS.
    if router.role == "border":
        lines.append(f"ipv6 route {as_obj.ipv6_prefix} Null0")

    # Configuration IGP
    if as_obj.protocol == "rip":
        lines.append(f"ipv6 router rip {as_obj.name}")
        lines.append("!")
    elif as_obj.protocol == "ospfv3":
        lines.append("ipv6 router ospf 1")
        lines.append(f" router-id {rid}")
        if router.role == "border" and inter_as_iface:
            lines.append(f" passive-interface {inter_as_iface}") # évite le partage d'ospf aux AS voisines 
        lines.append("!")

    lines.append("control-plane") # trafic d'infos destinées au router 
    lines.append("!")
    lines.append("line con 0") # permet d'entrer dans la configuration de la ligne console physique
    lines.append(" exec-timeout 0 0") # désactive le compte à rebours avant fermeture session cisco
    lines.append(" privilege level 15") # niveaux d'accès de 1 (très peu) à 15 (sudo)
    lines.append(" logging synchronous") # permet de pouvoir finir de taper ta commande sans te faire couper par la console en plein milieu de ta ligne !!
    lines.append(" stopbits 1") # chaque bit de fin de transmission de packet sera un 1
    lines.append("line aux 0") # entrer dans la configuration du port Auxiliaire du routeur.
    lines.append(" exec-timeout 0 0") ## alors la y a 2 fois les mêmes lignes mais on avait peur de les enlever et que ça marche plus... désolée 
    lines.append(" privilege level 15")
    lines.append(" logging synchronous")
    lines.append(" stopbits 1")
    lines.append("line vty 0 4")
    lines.append(" login")
    lines.append("!")
    lines.append("!")
    lines.append("end")

    return "\n".join(lines)

def main(intent_path, route_reflection = False):
    """
    Orchestre la génération complète des fichiers de configuration réseau à partir d'un fichier d'intention:
    1. Analyse le fichier JSON d'intention 
    2. Prépare les sous-réseaux IPv6 pour les liens Inter-AS
    3. Alloue les adresses IP et construit les topologies BGP 
    4. Nettoie et recrée le dossier de destination 'configs/'.
    5. Génère et sauvegarde chaque fichier de configuration 

    Args:
        intent_path (str): Chemin vers le fichier JSON 
        route_reflection : est-ce qu'on fait le réseau en full-mesh ou en route_reflection avec un routeur désigné reflector router ?

    Returns:
        None

    Notes:
        Les fichiers de sortie sont nommés selon le format 'i<num>_startup-config.cfg' 
        et stockés dans le répertoire local 'configs/'.
    """
    as_map = parse_intent(intent_path) # transforme en dico python
    inter_as_iterator = iter(ipaddress.IPv6Network("2001:100:100::/56").subnets(new_prefix=64)) # découpage en sous réseaux pour liens inter AS
    build_inter_as_neighbors(as_map, inter_as_iterator) # attribu addr IP lien inter AS 


    if os.path.exists("configs"):
       shutil.rmtree("configs") # supprime dossier s'il existe déjà
    os.makedirs("configs", exist_ok=True) # créer dossier 

    allocate_addresses(as_map) # affectation addr IP 
    if route_reflection : 
        build_bgp_rr(as_map)
    else : 
        build_bgp_fullmesh(as_map) # iBGP

    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            cfg = generate_router_config(router, as_obj, as_map, reflection_routing = route_reflection) 
            with open(f"configs/i{router.name[1:]}_startup-config.cfg", "w") as f: #création fichier avec bon nom 
                f.write(cfg) #écrit ce qu'il y a dans le template dans le fichier
            print(f"Generated i{router.name[1:]}_startup-config.cfg") #message de succes 


if __name__ == "__main__":
    # Ce bloc ne s'exécute QUE si je lance ce fichier précisément
    intent_path = "test.json"
    route_reflection = True ## Changez à votre guise
    main(intent_path, route_reflection)


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
    for as_obj in as_map.values():
        routers = list(as_obj.routers.values())
        for i in range(len(routers)):
            for j in range(i + 1, len(routers)):
                r1, r2 = routers[i], routers[j]
                r1.bgp_neighbors[str(r2.loopback)] = as_obj.asn
                r2.bgp_neighbors[str(r1.loopback)] = as_obj.asn


def build_inter_as_neighbors(as_map: Dict[str, AutonomousSystem]) -> None:
    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            for neigh in router.neighbors:
                if neigh.type == "inter-as":
                    remote_as_name, remote_router_name = neigh.router.split(":")
                    if remote_router_name > router.name: # pour pas faire deux fois
                        remote_as = as_map[remote_as_name]
                        remote_router = remote_as.routers[remote_router_name]

                        link_prefix = as_obj.allocate_link_prefix(inter_as=True)
                        r_ip = link_prefix[1]
                        n_ip = link_prefix[2]

                        router.interfaces[neigh.interface] = Interface(
                            name=neigh.interface,
                            ipv6=r_ip,
                            prefix_len=64,
                            ospf_area=as_obj.area if as_obj.protocol == "ospfv3" else None,
                            ripng=False
                        )

                        remote_iface = next(n.interface for n in remote_router.neighbors if n.router == f"{as_obj.name}:{router.name}")
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
    num = int(router_name.lstrip("R"))
    return f"{num}.{num}.{num}.{num}"

def determine_bgp_role(local_asn, remote_asn, bgp_policies):
    for role, as_list in bgp_policies["as_neighbors"].items():
        if remote_asn in as_list:
            return role
    return None



def generate_router_config(router: Router, as_obj: AutonomousSystem, as_map: Dict[str, AutonomousSystem]) -> str:
    rid = router_id_from_name(router.name)

    # Find inter-AS interface (if any)
    inter_as_iface = None
    for neigh in router.neighbors:
        if neigh.type == "inter-as":
            inter_as_iface = neigh.interface
            break
    
    # Map interface name -> ospf_cost (si défini)
    iface_costs = {
        n.interface: n.ospf_cost
        for n in router.neighbors
        if n.ospf_cost is not None and n.type == "intra-as"
    }

    # Mapping IP neighbor -> role
    bgp_role_by_ip = {}

    for neigh in router.neighbors:
        if neigh.type == "inter-as":
            # IP locale
            local_ip = router.interfaces[neigh.interface].ipv6

            # Trouver le router distant
            remote_as_name, remote_router_name = neigh.router.split(":")

            remote_as = as_map[remote_as_name]
            remote_router = remote_as.routers[remote_router_name]

            # Trouver l'interface du voisin qui pointe vers nous
            remote_iface_name = next(
                n.interface for n in remote_router.neighbors
                if n.router == f"{as_obj.name}:{router.name}"
            )

            remote_ip = remote_router.interfaces[remote_iface_name].ipv6

            # Mapping IP du voisin -> rôle
            bgp_role_by_ip[str(remote_ip)] = neigh.bgp_role
    #print(bgp_role_by_ip)

    lines = []
    lines.append("!")
    lines.append("version 15.2")
    lines.append("service timestamps debug datetime msec")
    lines.append("service timestamps log datetime msec")
    lines.append("!")
    lines.append(f"hostname {router.name}")
    lines.append("!")
    lines.append("boot-start-marker")
    lines.append("boot-end-marker")
    lines.append("!")
    lines.append("no aaa new-model")
    lines.append("no ip icmp rate-limit unreachable")
    lines.append("ip cef")
    lines.append("!")
    lines.append("no ip domain lookup")
    lines.append("ipv6 unicast-routing")
    lines.append("ipv6 cef")
    lines.append("!")
    lines.append("multilink bundle-name authenticated")
    lines.append("!")
    lines.append("ip tcp synwait-time 5")
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
        lines.append(" negotiation auto")
        lines.append(f" ipv6 address {iface.ipv6}/{iface.prefix_len}")
        lines.append(" ipv6 enable")

        if as_obj.protocol == "ospfv3":
            lines.append(f" ipv6 ospf {as_obj.process_id} area {iface.ospf_area}") #
            if iface.name in iface_costs: #
            #if hasattr(iface, "ospf_cost") and iface.ospf_cost is not None:

                lines.append(f" ipv6 ospf cost {iface_costs[iface.name]}") #

        if iface.ripng:
            lines.append(f" ipv6 rip {as_obj.name} enable")

        lines.append("!")

    
    # BGP
    lines.append(f"router bgp {router.asn}")
    lines.append(f" bgp router-id {rid}")
    lines.append(" bgp log-neighbor-changes")
    if router.role == "border":
        lines.append(" no synchronization")
    lines.append(" no bgp default ipv4-unicast")

    for neigh_ip, neigh_asn in router.bgp_neighbors.items():
        lines.append(f" neighbor {neigh_ip} remote-as {neigh_asn}")
        if neigh_asn == router.asn:
            lines.append(f" neighbor {neigh_ip} update-source Loopback0") # on n'ajoute cette ligne que pour notre as
    
    lines.append(" !")
    lines.append(" address-family ipv4")
    lines.append(" exit-address-family")
    lines.append(" !")
    lines.append(" address-family ipv6")

    if router.role == "border":
        lines.append(f"  network {as_obj.ipv6_prefix}")


    print(router.name,":",router.bgp_neighbors)
    for neigh_ip in router.bgp_neighbors.keys():
        role = bgp_role_by_ip.get(neigh_ip)

        lines.append(f"  neighbor {neigh_ip} activate")
        if router.bgp_neighbors[neigh_ip] == router.asn:
            lines.append(f"  neighbor {neigh_ip} next-hop-self")

        # Appliquer la policy selon le rôle (provider/peer/customer)
        if role:
            if role in as_obj.bgp_policies["policies"].get("communities", {}):
                lines.append(f"  neighbor {neigh_ip} send-community")
                lines.append(f"  neighbor {neigh_ip} route-map SET-COMMUNITY-{role} in")

            """if role in as_obj.bgp_policies["policies"].get("local_pref", {}):
                lines.append(f"  neighbor {neigh_ip} route-map SET-LOCALPREF-{role} in")
"""
            if role == "provider":
                lines.append(f"  neighbor {neigh_ip} route-map EXPORT-FILTER-provider out")


    lines.append(" exit-address-family")
    lines.append("!")



    """# Rôles BGP réellement présents sur ce routeur
    roles_present = set()

    for neigh in router.neighbors:
        if neigh.type == "inter-as":
            roles_present.add(neigh.bgp_role)
    # route-maps pour communities (uniquement si le rôle est présent)
    for role, comm in as_obj.bgp_policies["policies"]["communities"].items():
        if role not in roles_present:
            continue

        lines.append(f"route-map SET-COMMUNITY-{role} permit 10")
        lines.append(f" set community {comm}")
        lines.append(f" set local-preference {as_obj.bgp_policies["policies"]["local_pref"][role]}")
        lines.append("!")"""

    # Rôles BGP réellement présents sur ce routeur
    roles_present = set()
    for neigh in router.neighbors:
        if neigh.type == "inter-as" and neigh.bgp_role:
            roles_present.add(neigh.bgp_role)

    # --- community-lists ---
    for role in roles_present:
        comm = as_obj.bgp_policies["policies"]["communities"][role]
        lines.append(f"ip community-list standard ONLY-{role.upper()} permit {comm}")
        lines.append("!")

    # --- route-maps set community + local-pref ---
    for role in roles_present:
        comm = as_obj.bgp_policies["policies"]["communities"][role]
        lp = as_obj.bgp_policies["policies"]["local_pref"][role]

        lines.append(f"route-map SET-COMMUNITY-{role} permit 10")
        lines.append(f" set community {comm}")
        lines.append(f" set local-preference {lp}")
        """lines.append("!")
        lines.append(f"route-map SET-LOCALPREF-{role} permit 10")
        lines.append(f" set local-preference {lp}")
        lines.append("!")
"""


    # export filter (seulement si provider présent)
    """if "provider" in roles_present:
        comm = as_obj.bgp_policies["policies"]["communities"]["provider"]
        lines.append(f"ip community-list standard ONLY-EXPORT-provider permit {comm}")
        lines.append("!")
        lines.append("route-map EXPORT-FILTER-provider permit 10")
        lines.append(" match community ONLY-EXPORT-provider")
        lines.append("!")
        lines.append("route-map EXPORT-FILTER-provider deny 20")
        lines.append("!")"""
    
    if "provider" in roles_present:
        lines.append("route-map EXPORT-FILTER-provider deny 10")
        lines.append(" match community ONLY-PEER")
        lines.append("!")
        lines.append("route-map EXPORT-FILTER-provider deny 20")
        lines.append(" match community ONLY-PROVIDER")
        lines.append("!")
        lines.append("route-map EXPORT-FILTER-provider permit 30")
        lines.append("!")

    if "peer" in roles_present:
        lines.append("route-map EXPORT-FILTER-peer deny 10")
        lines.append(" match community ONLY-PEER")
        lines.append("!")
        lines.append("route-map EXPORT-FILTER-peer deny 20")
        lines.append(" match community ONLY-PROVIDER")
        lines.append("!")
        lines.append("route-map EXPORT-FILTER-peer permit 30")
        lines.append("!")


    lines.append("ip forward-protocol nd")
    lines.append("!")
    lines.append("no ip http server")
    lines.append("no ip http secure-server")
    lines.append("!")

    # Route statique vers le supernet (pour les routeurs border)
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
            lines.append(f" passive-interface {inter_as_iface}")
        lines.append("!")

    lines.append("control-plane")
    lines.append("!")
    lines.append("line con 0")
    lines.append(" exec-timeout 0 0")
    lines.append(" privilege level 15")
    lines.append(" logging synchronous")
    lines.append(" stopbits 1")
    lines.append("line aux 0")
    lines.append(" exec-timeout 0 0")
    lines.append(" privilege level 15")
    lines.append(" logging synchronous")
    lines.append(" stopbits 1")
    lines.append("line vty 0 4")
    lines.append(" login")
    lines.append("!")
    lines.append("!")
    lines.append("end")

    return "\n".join(lines)

def main(intent_path):
    #intent_path = "intent_file.json"
    as_map = parse_intent(intent_path)


    if os.path.exists("configs2"):
       shutil.rmtree("configs2") # Supprime le dossier s'il existe déjà
    os.makedirs("configs2", exist_ok=True)

    allocate_addresses(as_map)
    build_bgp_fullmesh(as_map)
    build_inter_as_neighbors(as_map)

    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            cfg = generate_router_config(router, as_obj, as_map)
            with open(f"configs2/i{router.name[1:]}_startup-config.cfg", "w") as f:
                f.write(cfg)
            print(f"Generated i{router.name[1:]}_startup-config.cfg")


if __name__ == "__main__":
    intent_path = "intent_9_routers.json"
    main(intent_path)

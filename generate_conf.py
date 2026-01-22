#!/usr/bin/env python3

import json
import ipaddress
from dataclasses import dataclass, field
import os
import shutil
from typing import Dict, List, Optional

@dataclass
class Interface:
    name: str
    ipv6: ipaddress.IPv6Address
    prefix_len: int
    ospf_area: Optional[int] = None
    ripng: bool = False
    ospf_cost: Optional[int] = None

@dataclass
class Neighbor:
    router: str
    type: str
    interface: str
    ospf_cost: Optional[int] = None 

@dataclass
class Router:
    name: str
    role: str
    asn: int
    neighbors: List[Neighbor]
    rr_role: Optional[str] = None  # "server" ou "client"
    loopback: Optional[ipaddress.IPv6Address] = None
    interfaces: Dict[str, Interface] = field(default_factory=dict)
    bgp_neighbors: Dict[str, int] = field(default_factory=dict)
    bgp_policies: Dict[str, Dict[str, str]] = field(default_factory=dict)

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

    def allocate_loopback(self) -> ipaddress.IPv6Address:
        used = {r.loopback for r in self.routers.values() if r.loopback}
        for ip in self.loopback_pool.hosts():
            if ip not in used:
                return ip
        raise ValueError("Loopback pool exhausted")

    def allocate_link_prefix(self, inter_as: bool = False) -> ipaddress.IPv6Network:
        pool = self.inter_as_link_pool if inter_as else self.link_pool
        subnets = list(pool.subnets(new_prefix=64))
        used = set()
        for r in self.routers.values():
            for iface in r.interfaces.values():
                net = ipaddress.IPv6Network(f"{iface.ipv6}/{iface.prefix_len}", strict=False)
                used.add(net.supernet(new_prefix=64))
        for net in subnets:
            if net not in used:
                return net
        raise ValueError("Link pool exhausted")

def parse_intent(path: str) -> Dict[str, AutonomousSystem]:
    data = json.load(open(path))
    as_map: Dict[str, AutonomousSystem] = {}

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
        )
        for rdata in as_data["routers"]:
            router = Router(
                name=rdata["name"],
                role=rdata["role"],
                rr_role=rdata.get("rr_role"), # Récupération du rôle RR
                asn=as_obj.asn,
                neighbors=[Neighbor(**n) for n in rdata.get("neighbors", [])]
            )
            as_obj.routers[router.name] = router
        as_map[as_obj.name] = as_obj

    # Logique des politiques BGP
    for as_data in data["autonomous_systems"]:
        local_as_name = as_data["name"]
        bgp_policies = as_data.get("bgp_policies", {})
        neighbors_policy = bgp_policies.get("as_neighbors", {})
        policies = bgp_policies.get("policies", {})

        as_roles = {}
        for role, remote_as_list in neighbors_policy.items():
            for remote_as in remote_as_list:
                as_roles[int(remote_as)] = role

        for router_data in as_data["routers"]:
            router = as_map[local_as_name].routers[router_data["name"]]
            for neigh in router.neighbors:
                if neigh.type == "inter-as":
                    remote_as_name, remote_router_name = neigh.router.split(":")
                    remote_asn = as_map[remote_as_name].asn
                    role = as_roles.get(remote_asn)
                    if not role: continue

                    policy = {}
                    if role in policies.get("communities", {}):
                        policy["set_community"] = policies["communities"][role]
                    if role in policies.get("local_pref", {}):
                        policy["local_pref"] = policies["local_pref"][role]
                    if role == "provider":
                        policy["export_only_community"] = policies["communities"]["provider"]

                    router.bgp_policies[remote_router_name] = policy

    return as_map

def allocate_addresses(as_map: Dict[str, AutonomousSystem]) -> None:
    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            router.loopback = as_obj.allocate_loopback()

    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            for neigh in router.neighbors:
                if neigh.type == "intra-as":
                    neigh_router = as_obj.routers[neigh.router]
                    if neigh.interface not in router.interfaces:
                        link_prefix = as_obj.allocate_link_prefix(inter_as=False)
                        router.interfaces[neigh.interface] = Interface(
                            name=neigh.interface, ipv6=link_prefix[1], prefix_len=64,
                            ospf_area=as_obj.area if as_obj.protocol == "ospfv3" else None,
                            ripng=(as_obj.protocol == "rip"),
                            ospf_cost=neigh.ospf_cost
                        )
                        remote_iface = next(n.interface for n in neigh_router.neighbors if n.router == router.name)
                        neigh_router.interfaces[remote_iface] = Interface(
                            name=remote_iface, ipv6=link_prefix[2], prefix_len=64,
                            ospf_area=as_obj.area if as_obj.protocol == "ospfv3" else None,
                            ripng=(as_obj.protocol == "rip"),
                            ospf_cost=neigh.ospf_cost
                        )

def build_bgp_sessions(as_map: Dict[str, AutonomousSystem]) -> None:
    for as_obj in as_map.values():
        routers = list(as_obj.routers.values())
        rr_servers = [r for r in routers if r.rr_role == "server"]
        
        if rr_servers:
            # Mode Route Reflector : Clients vers Serveurs
            for rr in rr_servers:
                for client in routers:
                    if rr.name != client.name:
                        rr.bgp_neighbors[str(client.loopback)] = as_obj.asn
                        client.bgp_neighbors[str(rr.loopback)] = as_obj.asn
        else:
            # Mode Full Mesh
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
                    if remote_router_name > router.name:
                        remote_as = as_map[remote_as_name]
                        remote_router = remote_as.routers[remote_router_name]
                        link_prefix = as_obj.allocate_link_prefix(inter_as=True)
                        
                        router.interfaces[neigh.interface] = Interface(
                            name=neigh.interface, ipv6=link_prefix[1], prefix_len=64
                        )
                        remote_iface = next(n.interface for n in remote_router.neighbors if n.router == f"{as_obj.name}:{router.name}")
                        remote_router.interfaces[remote_iface] = Interface(
                            name=remote_iface, ipv6=link_prefix[2], prefix_len=64
                        )
                        router.bgp_neighbors[str(link_prefix[2])] = remote_as.asn
                        remote_router.bgp_neighbors[str(link_prefix[1])] = as_obj.asn

def router_id_from_name(router_name: str) -> str:
    num = int(router_name.lstrip("R"))
    return f"{num}.{num}.{num}.{num}"

def generate_router_config(router: Router, as_obj: AutonomousSystem, as_map: Dict[str, AutonomousSystem]) -> str:
    rid = router_id_from_name(router.name)
    inter_as_iface = next((n.interface for n in router.neighbors if n.type == "inter-as"), None)

    lines = [
        "!", "version 15.2", "service timestamps debug datetime msec",
        "service timestamps log datetime msec", "!", f"hostname {router.name}", "!",
        "ip cef", "no ip domain lookup", "ipv6 unicast-routing", "ipv6 cef", "!",
        "interface Loopback0", " no ip address", " no shutdown",
        f" ipv6 address {router.loopback}/128", " ipv6 enable"
    ]
    
    if as_obj.protocol == "ospfv3":
        lines.append(f" ipv6 ospf {as_obj.process_id} area {as_obj.area}")
    elif as_obj.protocol == "rip":
        lines.append(f" ipv6 rip {as_obj.name} enable")
    lines.append("!")

    # --- Interfaces Physiques ---
    for iface in router.interfaces.values():
        lines.append(f"interface {iface.name}")
        lines.append(" no ip address\n no shutdown\n negotiation auto")
        lines.append(f" ipv6 address {iface.ipv6}/{iface.prefix_len}\n ipv6 enable")
        
        # IGP sur interfaces intra-as
        if as_obj.protocol == "ospfv3" and iface.ospf_area is not None:
            lines.append(f" ipv6 ospf {as_obj.process_id} area {iface.ospf_area}")
            if iface.ospf_cost: 
                lines.append(f" ipv6 ospf cost {iface.ospf_cost}")
        if iface.ripng:
            lines.append(f" ipv6 rip {as_obj.name} enable")
        lines.append("!")

    # --- Configuration BGP ---
    lines.append(f"router bgp {router.asn}")
    lines.append(f" bgp router-id {rid}")
    lines.append(" no bgp default ipv4-unicast")

    # Déclaration des voisins (Global)
    for neigh_ip, neigh_asn in router.bgp_neighbors.items():
        lines.append(f" neighbor {neigh_ip} remote-as {neigh_asn}")
        if neigh_asn == router.asn:
            lines.append(f" neighbor {neigh_ip} update-source Loopback0")
            if router.rr_role == "server":
                lines.append(f" neighbor {neigh_ip} route-reflector-client")

    lines.append(" !")
    lines.append(" address-family ipv6")
    
    if router.role == "border":
        lines.append(f"  network {as_obj.ipv6_prefix}")

    # Activation et Politiques par Address-Family
    for neigh_ip, neigh_asn in router.bgp_neighbors.items():
        lines.append(f"  neighbor {neigh_ip} activate")
        
        if neigh_asn == router.asn:
            lines.append(f"  neighbor {neigh_ip} next-hop-self")
        else:
            # EBGP : Chercher la politique associée au routeur distant
            target_router_name = None
            for r_name in router.bgp_policies.keys():
                # On vérifie si l'IP du voisin appartient au routeur nommé r_name
                for target_as in as_map.values():
                    if r_name in target_as.routers:
                        rem_router = target_as.routers[r_name]
                        if any(str(i.ipv6) == neigh_ip for i in rem_router.interfaces.values()):
                            target_router_name = r_name
                            break
            
            if target_router_name:
                pol = router.bgp_policies[target_router_name]
                if "set_community" in pol or "export_only_community" in pol:
                    lines.append(f"  neighbor {neigh_ip} send-community")
                    lines.append(f"  neighbor {neigh_ip} route-map RM-OUT-{target_router_name} out")
                if "local_pref" in pol:
                    lines.append(f"  neighbor {neigh_ip} route-map RM-IN-{target_router_name} in")

    lines.append("  exit-address-family")
    lines.append("!")

    # --- Route Statique pour Border ---
    if router.role == "border":
        lines.append(f"ipv6 route {as_obj.ipv6_prefix} Null0")

    # --- Configuration IGP (Processus) ---
    if as_obj.protocol == "rip":
        lines.append(f"ipv6 router rip {as_obj.name}")
    elif as_obj.protocol == "ospfv3":
        lines.append(f"ipv6 router ospf {as_obj.process_id}\n router-id {rid}")
        if router.role == "border" and inter_as_iface:
            lines.append(f" passive-interface {inter_as_iface}")
    lines.append("!")

    # --- Génération des Route-Maps et Community-Lists ---
    for r_name, pol in router.bgp_policies.items():
        # Politique entrante (Local Preference)
        if "local_pref" in pol:
            lines.append(f"route-map RM-IN-{r_name} permit 10")
            lines.append(f" set local-preference {pol['local_pref']}")
            lines.append("!")
        
        # Politique sortante (Community)
        if "set_community" in pol:
            lines.append(f"route-map RM-OUT-{r_name} permit 10")
            lines.append(f" set community {pol['set_community']}")
            lines.append("!")
        
        # Filtre d'export (si provider)
        if "export_only_community" in pol:
            comm = pol["export_only_community"]
            lines.append(f"ipv6 community-list standard L-ONLY-{r_name} permit {comm}")
            lines.append(f"route-map RM-OUT-{r_name} permit 20")
            lines.append(f" match community L-ONLY-{r_name}")
            lines.append("!")

    lines.append("end")
    return "\n".join(lines)

def main(intent_path):
    as_map = parse_intent(intent_path)
    if os.path.exists("configs"): shutil.rmtree("configs")
    os.makedirs("configs", exist_ok=True)

    allocate_addresses(as_map)
    build_bgp_sessions(as_map)
    build_inter_as_neighbors(as_map)

    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            cfg = generate_router_config(router, as_obj, as_map)
            with open(f"configs/i{router.name[1:]}_startup-config.cfg", "w") as f:
                f.write(cfg)
            print(f"Generated i{router.name[1:]}_startup-config.cfg")

if __name__ == "__main__":
    intent_path = 'test.json'
    main(intent_path)

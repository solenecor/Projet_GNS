def build_inter_as_neighbors(as_map: Dict[str, AutonomousSystem], inter_as_iterator) -> None:
    for as_obj in as_map.values():
        for router in as_obj.routers.values():
            for neigh in router.neighbors:
                if neigh.type == "inter-as":
                    remote_as_name, remote_router_name = neigh.router.split(":")
                    if remote_router_name > router.name:  # pour pas faire deux fois
                        remote_as = as_map[remote_as_name]
                        remote_router = remote_as.routers[remote_router_name]

                        # On récupère un /64 unique depuis l'itérateur global
                        link_prefix = next(inter_as_iterator)
                        print(f"🔗 Attribution inter-AS {router.name} <-> {remote_router_name} : {link_prefix}")

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

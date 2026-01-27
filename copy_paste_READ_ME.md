## Tests de fonctionnement

---

### Vérifier les interfaces et adresses IPv6


```bash
show ipv6 interface brief

```

**vérifié si:** Toutes les interfaces sont **"up/up"** avec les bonnes **adresses IPv6** (loopback et liens)

---

###  Vérifier RIPng (AS1 : R1, R2, R3)


```bash
show ipv6 rip [AS1] database
show ipv6 route rip

```

**vérifié si:**  il y a ripng dans la database de l'AS1, AS3, AS4 et AS5 et des routes avec le code `R` après avoir affiché les routes.

---

### Vérifier OSPFv3 (AS2 : R4, R5, R6)


```bash
show ipv6 ospf neighbor
show ipv6 ospf interface
show ipv6 route ospf

```

**vérifié si:**  il y a des voisins OSPF en état `FULL/DR`, `FULL/BDR` , les **coûts OSPF** corrects au réseau (dans notre réseau, on a mis 10), des routes avec le code `O` dans `show ipv6 route`

---

### Vérifier les sessions BGP (R3, R4)

```bash
show bgp ipv6 unicast summary

```

**vérifié si:**  il y a des voisins BGP listés, le **state** à `Established` et des **routes reçues** entre les AS, pour vérifier les routes BGP, `show bgp ipv6 unicast`, il faut appercevoir les préfixes BGP reçus et le **next-hop**, **AS_PATH**, **LocPrf**
 




---

### Vérifier les communities BGP

```bash
show bgp ipv6 unicast neighbors <ip> received-routes
show bgp ipv6 unicast neighbors <ip> advertised-routes

```

avec `| include Community` pour filtrer :

```bash
show bgp ipv6 unicast neighbors <ip> received-routes | include Community

```

**vérifié si:**  il y a des **communities** ( `1:100`, `2:200`) (ou leur version décimale : - `1:100` = 1\times 65536+100=65636
- `1:200` = 1\times 65536+200=65736) et les routes taggées 
---

### Vérifier les route-maps et community-lists

```bash
show run | section route-map
show run | include community-list

```

**vérifié si:**  il y a les `route-map SET-COMMUNITY-...`, `SET-LOCALPREF-...`, `EXPORT-FILTER-...` et les `ip community-list` avec les bons IDs

---

### Vérifier les routes exportées

### Commande sur R3 :

```bash
show bgp ipv6 unicast neighbors 2001:100:100::2 advertised-routes

```

**vérifié si:**  seules les routes autorisées par `EXPORT-FILTER` sont envoyées et les bonnes communities sont présentes

---

### Vérifier la connectivité entre 2 routeurs 


```bash
ping ipv6 <loopback_router_1>
traceroute ipv6 <loopback_router2>

```

**vérifié si:**  le ping réussit et le traceroute suit le **chemin OSPF avec les bons coûts**


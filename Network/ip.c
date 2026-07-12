#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>

int main() {
  struct in_addr address1;
  struct in6_addr address2;
  inet_pton(AF_INET, "10.12.110.57", &address1);
  inet_pton(AF_INET6, "2001:db8:63b3:1::3490", &address2);
  printf("ipv4 binary representation: \n%d\n", address1.s_addr);
  printf("ipv6 binary representation: \n%s\n", address2.s6_addr);

  char ip4[INET_ADDRSTRLEN];
  char ip6[INET6_ADDRSTRLEN];
  inet_ntop(AF_INET, &address1, ip4, INET_ADDRSTRLEN);
  inet_ntop(AF_INET6, &address2, ip6, INET6_ADDRSTRLEN);
  printf("ipv4: \n%s\n", ip4);
  printf("ipv6: \n%s\n", ip6);

  char web_url[] = "www.example.net";
  char web_url_unexist[] = "www.nosuchweb.com";
  struct addrinfo hints, *res, *p;
  int status;
  char ipstr[INET6_ADDRSTRLEN];
  memset(&hints, 0, sizeof hints);
  if ((status = getaddrinfo(web_url_unexist, NULL, &hints, &res)) != 0) {
    fprintf(stderr, "getaddrinfo: %s:\n", gai_strerror(status));
  }
  memset(&hints, 0, sizeof hints);
  if ((status = getaddrinfo(web_url, NULL, &hints, &res)) != 0) {
    fprintf(stderr, "getaddrinfo: %s:\n", gai_strerror(status));
    return 1;
  }
  for (p = res; p != NULL; p = p->ai_next) {
    void *addr;
    char *ipver;
    struct sockaddr_in *ipv4_sock;
    struct sockaddr_in6 *ipv6_sock;
    if (p->ai_family == AF_INET) {
      ipv4_sock = (struct sockaddr_in *)p->ai_addr;
      addr = &(ipv4_sock->sin_addr);
      ipver = "IPv4";
    } else {
      ipv6_sock = (struct sockaddr_in6 *)p->ai_addr;
      addr = &(ipv6_sock->sin6_addr);
      ipver = "IPv6";
    }
    inet_ntop(p->ai_family, addr, ipstr, sizeof ipstr);
    printf(" %s: %s\n", ipver, ipstr);
  }
  return 0;
}

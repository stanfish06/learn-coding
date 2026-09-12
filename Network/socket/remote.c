#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

int main() {
  struct addrinfo hints, *res;
  int s;
  memset(&hints, 0, sizeof hints);
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_DGRAM; // or STREAM

  // create a listen socket on 0.0.0.0 on that machine first
  getaddrinfo("100.95.231.79", "8090", &hints, &res);
  s = socket(res->ai_family, res->ai_socktype, res->ai_protocol);

  char buf[1024];
  if (connect(s, res->ai_addr, res->ai_addrlen) == 0) {
    printf("connected!\n");
    const char *msg = "hello there\n";
    send(s, msg, strlen(msg), 0);
    int n = recv(s, buf, sizeof buf - 1, 0);
    if (n > 0) {
      buf[n] = '\0';
      printf("received: %s\n", buf);
    }
  }
  close(s);
}

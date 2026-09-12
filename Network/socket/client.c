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
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_flags = AI_PASSIVE;

  getaddrinfo(NULL, "2390", &hints, &res);
  s = socket(res->ai_family, res->ai_socktype, res->ai_protocol);

  char buf[1024];
  const char *msg = "hello from client\n";
  if (connect(s, res->ai_addr, res->ai_addrlen) == 0) {
    send(s, msg, strlen(msg), 0);
    int n = recv(s, buf, sizeof buf - 1, 0);
    if (n > 0) {
      buf[n] = '\0';
      printf("received: %s\n", buf);
    }
  };
  close(s);
}

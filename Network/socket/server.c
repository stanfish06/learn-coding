#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

int main() {
  int s, s2;
  struct addrinfo hints, *res, *p;
  memset(&hints, 0, sizeof hints);
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_flags = AI_PASSIVE;
  // NULL means current host
  int status;
  if ((status = getaddrinfo(NULL, "2390", &hints, &res)) != 0) {
    fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(status));
    return 1;
  }

  for (p = res; p != NULL; p = p->ai_next) {
    s = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
    if (s == -1)
      continue;
    int yes = 1;
    // kernel reserves port for previous socket for a while so bind could fail
    // specify SO_REUSEADDR let you bind anyway in that period
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof yes);
    if (bind(s, p->ai_addr, p->ai_addrlen) == 0)
      break;
    close(s);
  }
  if (p == NULL) {
    fprintf(stderr, "failed to bind\n");
    return 1;
  }
  freeaddrinfo(res);

  if (listen(s, 5) == -1) {
    perror("listen");
    return 1;
  }
  printf("listening on port 2390...\n");

  s2 = accept(s, NULL, NULL);
  if (s2 == -1) {
    perror("accept");
    return 1;
  }
  printf("got a connection!\n");

  char buf[1024];
  int n = recv(s2, buf, sizeof buf - 1, 0);
  if (n > 0) {
    buf[n] = '\0';
    printf("received: %s\n", buf);
    const char *reply = "hello from server\n";
    send(s2, reply, strlen(reply), 0);
  }

  close(s2);
  close(s);
  return 0;
}

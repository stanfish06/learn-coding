#include <netdb.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#define NUM 500
#define PAYLOAD 800

int main(int argc, char *argv[]) {
  const char *host = argc > 1 ? argv[1] : "100.95.231.79";

  struct addrinfo hints, *res;
  memset(&hints, 0, sizeof hints);
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_DGRAM;

  int status;
  if ((status = getaddrinfo(host, "8090", &hints, &res)) != 0) {
    fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(status));
    return 1;
  }
  int s = socket(res->ai_family, res->ai_socktype, res->ai_protocol);

  for (int i = 0; i < NUM; i++) {
    char msg[PAYLOAD + 32];
    int len = snprintf(msg, sizeof msg, "pkt %04d ", i);
    memset(msg + len, 'x', PAYLOAD);
    sendto(s, msg, len + PAYLOAD, 0, res->ai_addr, res->ai_addrlen);
  }
  printf("sent %d packets, waiting for echoes...\n", NUM);

  int got[NUM] = {0}, total = 0;
  for (;;) {
    char buf[PAYLOAD + 64];
    struct timeval tv = {.tv_sec = 1};
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    int n = recvfrom(s, buf, sizeof buf - 1, 0, NULL, NULL);
    if (n <= 0)
      break;
    buf[n] = '\0';
    int seq = -1;
    char *found = strstr(buf, "pkt");
    if (found)
      sscanf(found, "pkt %d", &seq);
    if (seq >= 0 && seq < NUM && !got[seq]) {
      got[seq] = 1;
      total++;
    }
  }

  printf("got back %d/%d (loss %.1f%%)\nmissing:", total, NUM,
         100.0 * (NUM - total) / NUM);
  for (int i = 0; i < NUM; i++)
    if (!got[i])
      printf(" %d", i);
  printf("\n");

  freeaddrinfo(res);
  close(s);
  return 0;
}

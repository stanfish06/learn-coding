#include <omp.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

int main() {
  int i, n;
  double a[100], b[100], income, bank;

  n = 100;
  for (int i = 0; i < n; i++) {
    a[i] = b[i] = i * 1.0;
  }
  income = 0.0;
  bank = 100.0;
  
  for (int i = 0; i < n; i++) {
    double income_curr = a[i] * b[i];
    income += income_curr;
    bank *= 1.01;
    if (i % 2 == 0) {
      double deposit = income_curr * 0.8;
      bank += deposit;
      income -= deposit; 
    }
  }
  printf("bank is %f\n", bank);
  printf("income is %f\n", income);
  
  income = 0.0;
  double  deposit_total = 0.0;
  double rate = 1.0;
  bank = 100.0;
  
#pragma omp parallel for reduction(+:income) reduction(*:rate) reduction(+:deposit_total)
  for (int i = 0; i < n; i++) {
    double income_curr = a[i] * b[i];
    income += income_curr;
    rate *= 1.01;
    if (i % 2 == 0) {
      double deposit = income_curr * 0.8;
      int n_compound = n - 1 - i;
      deposit_total += deposit * pow(1.01, n_compound);
      income -= deposit; 
    }
  }
  bank = rate * bank;
  bank += deposit_total;
  printf("bank is %f\n", bank);
  printf("income is %f\n", income);
}

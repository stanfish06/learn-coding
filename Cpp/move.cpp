#include <iostream>
#include <string>
#include <utility>
#include <vector>

template <typename T> void swap(T &a, T &b) {
  T tmp{std::move(a)};
  a = std::move(b);
  b = std::move(tmp);
}

void whats_in_plate(std::vector<std::string> &plate) {
  std::cout << "your plate:" << std::endl;
  for (const auto &dish : plate) {
    std::cout << dish << " ";
  }
  std::cout << std::endl;
}

int main() {
  std::string dish1 = "burger";
  std::string dish2 = "taco";
  std::cout << "first dish is: " << dish1 << std::endl;
  std::cout << "second dish is: " << dish2 << std::endl;
  swap(dish1, dish2);
  std::cout << "swap dish..." << std::endl;
  std::cout << "first dish is: " << dish1 << std::endl;
  std::cout << "second dish is: " << dish2 << std::endl;

  std::vector<std::string> plate = {"steak", "egg"};
  whats_in_plate(plate);

  std::cout << "copy " << dish1 << " into my plate" << std::endl;
  plate.push_back(dish1);
  whats_in_plate(plate);
  std::cout << dish1 << " is still there" << std::endl;

  std::cout << "move " << dish1 << " into my plate" << std::endl;
  plate.push_back(std::move(dish1));
  whats_in_plate(plate);
  std::cout << dish1 << " is gone" << std::endl;
}

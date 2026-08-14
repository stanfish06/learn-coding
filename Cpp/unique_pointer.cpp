#include <iostream>
#include <memory>
#include <string>

class Resource {
  std::string user{"unknown"};

public:
  Resource(std::string user) {
    if (user != "") {
      this->user = user;
    }
    std::cout << "resource allocated for " << this->user << std::endl;
  };
  ~Resource() {
    std::cout << "resource deleted for " << this->user << std::endl;
  };
  void hello() { std::cout << "hello " << this->user << std::endl; };
  void setUser(std::string user) { this->user = user; };
  std::string getUser() { return this->user; };
};

// use unique_ptr's cast to bool to check if unique_ptr is holding a resource
// instance
void safe_hello(std::unique_ptr<Resource> &ptr) {
  if (ptr) {
    ptr->hello();
  } else {
    std::cout << "pointer is not holding resource" << std::endl;
  }
};

void take_resource(std::unique_ptr<Resource> ptr) {
  if (ptr) {
    Resource &rs = *ptr;
    rs.hello();
  }
}

std::ostream &operator<<(std::ostream &out, const Resource &) {
  out << "I am a resource";
  return out;
}

void view_resource(std::unique_ptr<Resource> &ptr) {
  if (ptr) {
    std::cout << *ptr << std::endl;
  }
}

std::unique_ptr<Resource> give_stan_resource() {
  return std::make_unique<Resource>("Stan");
}

int main() {
  Resource *ptr_tommy = new Resource("tommy");
  ptr_tommy->hello();
  std::unique_ptr<Resource> ptr_tommy_move{ptr_tommy};
  // these are still valid, standard pointer can still read/write
  ptr_tommy->hello();
  ptr_tommy->setUser("jimmy");
  ptr_tommy_move->hello();

  auto ptr_cj = std::make_unique<Resource>("cj");
  std::unique_ptr<Resource> ptr_cj_move{};
  std::cout << "ptr_cj is " << (ptr_cj ? "not null" : "null") << std::endl;
  std::cout << "ptr_cj_move is " << (ptr_cj_move ? "not null" : "null")
            << std::endl;
  safe_hello(ptr_cj);
  safe_hello(ptr_cj_move);
  ptr_cj_move = std::move(ptr_cj);
  std::cout << "ptr_cj is " << (ptr_cj ? "not null" : "null") << std::endl;
  std::cout << "ptr_cj_move is " << (ptr_cj_move ? "not null" : "null")
            << std::endl;
  safe_hello(ptr_cj);
  safe_hello(ptr_cj_move);

  auto ptr_michael = std::make_unique<Resource>("michael");
  safe_hello(ptr_michael);
  view_resource(ptr_michael);
  safe_hello(ptr_michael);
  take_resource(std::move(ptr_michael));
  safe_hello(ptr_michael);

  auto ptr_stan = give_stan_resource();
  safe_hello(ptr_stan);
  return 0;
}

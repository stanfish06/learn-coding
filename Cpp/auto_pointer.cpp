#include <iostream>
#include <string>

template <typename T> class Auto_ptr {
  T *m_ptr{};

public:
  Auto_ptr(T *ptr = nullptr) : m_ptr(ptr) {};
  Auto_ptr(Auto_ptr &ptr_src) {
    m_ptr = ptr_src.m_ptr;
    ptr_src.m_ptr = nullptr;
  };

  ~Auto_ptr() { delete m_ptr; };

  T &operator*() const { return *m_ptr; };
  T *operator->() const { return m_ptr; };
  Auto_ptr &operator=(Auto_ptr &ptr_src) {
    if (&ptr_src == this)
      return *this;
    // deallocate whatever this ptr holds
    delete m_ptr;
    m_ptr = ptr_src.m_ptr;
    ptr_src.m_ptr = nullptr;
    return *this;
  };
};

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

void greet() {
  Auto_ptr<Resource> ptr(new Resource(""));
  std::string name;
  std::cout << "whats ur name?" << std::endl;
  std::cin >> name;
  ptr->setUser(name);

  if (ptr->getUser() == "Stan") {
    std::cout << "oh no" << std::endl;
    return;
  }
  ptr->hello();
}

int main() {
  Auto_ptr<Resource> *ptr_tommy = new Auto_ptr<Resource>(new Resource("tommy"));
  delete ptr_tommy;
  Auto_ptr<Resource> ptr_cj(new Resource("cj"));
  // without moving ownership to ptr_cj_clone (e.g. without that = op override
  // above), a second delete happens after cj is gone
  // Auto_ptr<Resource> ptr_cj_clone = ptr_cj;
  Auto_ptr<Resource> ptr_cj_clone(ptr_cj);
  Auto_ptr<Resource> ptr_cj_clone_clone = ptr_cj_clone;

  greet();
  return 0;
};

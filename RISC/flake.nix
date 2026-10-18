{
  description = "RISC-V dev shell";
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
  };
  outputs =
    { self, nixpkgs, ... }@inputs:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      llvm = pkgs.llvmPackages;
    in
    {
      devShells.${system} = {
        default = pkgs.mkShell {
          packages = [
            llvm.clang-unwrapped
            llvm.lld
            llvm.llvm
            llvm.lldb
            pkgs.qemu
          ];
        };
      };
    };
}

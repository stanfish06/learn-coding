{
  description = "dev shell";
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
  };
  outputs =
    { self, nixpkgs, ... }@inputs:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
    in
    {
      devShells.${system} = {
        default = pkgs.mkShell {
          packages = with pkgs; [
            minikube
            kubernetes-helm
            jq
            (writeShellScriptBin "kubectl" ''exec ${minikube}/bin/minikube kubectl -- "$@"'')
          ];
          shellHook = ''
            . <(minikube completion bash)
            . <(helm completion bash)

            # kubectl and docker completion require the control plane to be running
            if [ "$(minikube status -o json 2>/dev/null | jq -r .Host)" = "Running" ]; then
                    . <(kubectl completion bash)
                    . <(minikube -p minikube docker-env)
            fi
          '';
        };
      };
    };
}

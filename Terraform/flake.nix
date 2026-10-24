{
  description = "Terraform + AWS dev shell";
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
  };
  outputs =
    { self, nixpkgs, ... }@inputs:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        # terraform is BSL-licensed, marked unfree in nixpkgs
        config.allowUnfreePredicate = pkg: builtins.elem (nixpkgs.lib.getName pkg) [ "terraform" ];
      };
    in
    {
      devShells.${system} = {
        default = pkgs.mkShell {
          packages = with pkgs; [
            terraform
            terraform-ls
            tflint
            awscli2
            jq
          ];
          shellHook = ''
            complete -C ${pkgs.terraform}/bin/terraform terraform
            complete -C ${pkgs.awscli2}/bin/aws_completer aws

            # share downloaded providers across exercise dirs
            export TF_PLUGIN_CACHE_DIR="$HOME/.cache/terraform/plugins"
            mkdir -p "$TF_PLUGIN_CACHE_DIR"
          '';
        };
      };
    };
}

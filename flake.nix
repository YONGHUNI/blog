{
  description = "Quarto research blog development tools (Pixi runtime)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          pkgs.bashInteractive
          pkgs.pixi
          pkgs.quarto
          pkgs.git
        ];
      };
    };
}

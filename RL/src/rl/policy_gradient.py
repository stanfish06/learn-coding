import gymnasium as gym
import argparse
import torch

torch.manual_seed(42)

def cartpole(task: str):
    env = gym.make("CartPole-v1", render_mode="rgb_array")
    env.reset(seed=42)
    match task:
        case "info":
            print("Observation space: ", env.observation_space)
            print("Action space: ", env.action_space)


ap = argparse.ArgumentParser()
ap.add_argument("--cartpole", default=False, action="store_true")
ap.add_argument("--task", type=str, default="")

def main():
    args = ap.parse_args()
    if args.cartpole:
        cartpole(args.task)

if __name__ == "__main__":
    main()

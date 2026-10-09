import gymnasium as gym
import argparse
import torch
import matplotlib.pyplot as plt

torch.manual_seed(42)


def cartpole(task: str):
    env = gym.make("CartPole-v1", render_mode="rgb_array")
    env.reset(seed=42)
    match task:
        case "info":
            print("Observation space: ", env.observation_space)
            print("Action space: ", env.action_space)
        case "demo":
            _, axes = plt.subplots(1, 4, figsize=(16, 4))
            axes[0].imshow(env.render())
            axes[0].set_title("initial state")
            axes[0].axis("off")
            for step in range(3):
                action = env.action_space.sample()
                next_state, reward, terminated, truncated, _ = env.step(action)
                axes[step + 1].imshow(env.render())
                axes[step + 1].set_title(
                    f"Step {step + 1}, {'LEFT' if action == 0 else 'RIGHT'}"
                )
                axes[step + 1].axis("off")
                print(f"Reward: {reward}")
            plt.savefig("cartpole_demo.png", dpi=300, bbox_inches="tight")


ap = argparse.ArgumentParser()
ap.add_argument("--cartpole", default=False, action="store_true")
ap.add_argument("--task", type=str, default="")


def main():
    args = ap.parse_args()
    if args.cartpole:
        cartpole(args.task)


if __name__ == "__main__":
    main()

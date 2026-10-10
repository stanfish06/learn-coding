import gymnasium as gym
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import matplotlib.pyplot as plt
from collections import deque
from torch.distributions import Categorical

torch.manual_seed(42)


class Policy(nn.Module):
    def __init__(self):
        super(Policy, self).__init__()
        self.affine1 = nn.Linear(4, 128)
        self.affine2 = nn.Linear(128, 2)

    def forward(self, x):
        x = self.affine1(x)
        x = F.relu(x)
        action_scores = self.affine2(x)
        return F.softmax(action_scores, dim=1)


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
        case "train":
            policy = Policy()
            state, _ = env.reset()
            state_tensor = torch.from_numpy(state).float().unsqueeze(0)
            probs = policy(state_tensor)
            print("State:", state)
            print("Action probs: [left, right] ", probs.detach().numpy()[0])

            optimizer = optim.Adam(policy.parameters(), lr=1e-3)
            n_epochs = 10_000
            n_steps = 10_000
            discount_gamma = 0.99
            running_reward = 10
            log_interval = 10
            reward_history = []

            for i in range(n_epochs):
                state, _ = env.reset()
                ep_reward = 0

                log_probs, rewards = [], []
                for t in range(1, n_steps):
                    state = torch.tensor(state).unsqueeze(0)
                    probs = policy(state)
                    p = Categorical(probs)
                    action = p.sample()
                    log_prob = p.log_prob(action)

                    state, reward, terminated, truncated, _ = env.step(action.item())
                    log_probs.append(log_prob)
                    rewards.append(reward)
                    ep_reward += reward
                    if terminated or truncated:
                        break

                returns = deque()
                R = 0
                for r in rewards[::-1]:
                    R = r + discount_gamma * R
                    returns.appendleft(R)
                returns = torch.tensor(returns)

                log_probs = torch.cat(log_probs)
                policy_loss = -(log_probs * returns).sum()

                optimizer.zero_grad()
                policy_loss.backward()
                optimizer.step()

                running_reward = 0.05 * ep_reward + (1 - 0.05) * running_reward
                reward_history.append(running_reward)

                if i % log_interval == 0:
                    print(
                        f"{i}\tLast reward; {ep_reward:.2f}\tAverage reward: {running_reward:.2f}"
                    )
                if running_reward > env.spec.reward_threshold:
                    print(
                        f"Solved. Running reward {running_reward:.2f} and hte last epoch runs to {t} time steps."
                    )
                    break
            _, ax = plt.subplots(1, 1, figsize=(10, 5))
            ax.plot(reward_history)
            ax.axhline(y=env.spec.reward_threshold, color="r", linestyle="--")
            plt.savefig("cartpole_train.png", dpi=300, bbox_inches="tight")


ap = argparse.ArgumentParser()
ap.add_argument("--cartpole", default=False, action="store_true")
ap.add_argument("--task", type=str, default="")


def main():
    args = ap.parse_args()
    if args.cartpole:
        cartpole(args.task)


if __name__ == "__main__":
    main()

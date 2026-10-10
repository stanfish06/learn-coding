import gymnasium as gym
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import matplotlib.pyplot as plt
from collections import deque
from torch.distributions import Categorical
import re

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


def grpo(task: str, adapter: str = ""):
    from datasets import load_dataset

    model_id = "Qwen/Qwen2-0.5B-Instruct"
    output_dir = "Qwen2-0.5B-GRPO-vllm-trl"

    dataset_id = "AI-MO/NuminaMath-TIR"
    train_dataset, test_dataset = load_dataset(
        dataset_id, split=["train[:10%]", "test[:10%]"]
    )
    SYS_PROMPT = (
        "A conversation between User and Assistant. The user asks a question, and the Assistant solves it. The assistant "
        "first thinks about the reasoning process in the mind and then provides the user with the answer. The reasoning "
        "process and answer are enclosed within <think> </think> and <answer> </answer> tags, respectively, i.e., "
        "<think> reasoning process here </think><answer> answer here </answer>"
    )

    def make_conversation(input):
        return {
            "prompt": [
                {"role": "system", "content": SYS_PROMPT},
                {"role": "user", "content": input["problem"]},
            ]
        }

    # pattern reward
    def format_reward(completions, **kwargs):
        pattern = r"^<think>.*?</think>\s*<answer>.*?</answer>$"
        completion_contents = [completion[0]["content"] for completion in completions]
        matches = [
            re.match(pattern, content, re.DOTALL) for content in completion_contents
        ]
        rewards_list = [1.0 if match else 0.0 for match in matches]
        return rewards_list

    def accuracy_reward(completions, **kwargs):
        from math_verify import LatexExtractionConfig, parse, verify

        solutions = kwargs["solution"]
        completion_contents = [completion[0]["content"] for completion in completions]
        rewards = []
        for content, solution in zip(completion_contents, solutions):
            gold_parsed = parse(
                solution,
                extraction_mode="first_match",
                extraction_config=[LatexExtractionConfig()],
            )
            answer_parsed = parse(
                content,
                extraction_mode="first_match",
                extraction_config=[LatexExtractionConfig()],
            )
            if len(gold_parsed) != 0:
                try:
                    rewards.append(float(verify(answer_parsed, gold_parsed)))
                except:
                    rewards.append(0.0)
            else:
                rewards.append(1.0)
        return rewards

    match task:
        case "info":
            print(train_dataset)
            print(train_dataset[0])
        case "train":
            train_dataset = train_dataset.map(make_conversation)
            train_dataset = train_dataset.remove_columns(["messages", "problem"])
            test_dataset = test_dataset.map(make_conversation)
            test_dataset = test_dataset.remove_columns(["messages", "problem"])
            print(train_dataset[0]["prompt"])
            print(train_dataset)

            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model = AutoModelForCausalLM.from_pretrained(
                model_id, dtype=torch.float16, device_map="auto"
            )
            tokenizer = AutoTokenizer.from_pretrained(model_id)

            from peft import LoraConfig, get_peft_model

            lora_config = LoraConfig(
                task_type="CAUSAL_LM",
                r=8,
                lora_alpha=32,
                lora_dropout=0.1,
                target_modules=["q_proj", "v_proj"],
            )

            model = get_peft_model(model, lora_config)
            model.print_trainable_parameters()

            from trl import GRPOConfig

            training_args = GRPOConfig(
                output_dir=output_dir,
                learning_rate=1e-5,
                gradient_accumulation_steps=16,
                num_train_epochs=1,
                max_completion_length=512,
                num_generations=8,
                report_to=["trackio"],
                project=output_dir,
                push_to_hub=True,
                trackio_static_space_id=False,
                save_strategy="steps",
                save_steps=50,
                fp16=True,
                bf16=False,
                use_vllm=True,
                vllm_mode="colocate",
            )

            from trl import GRPOTrainer

            trainer = GRPOTrainer(
                model=model,
                reward_funcs=[format_reward, accuracy_reward],
                args=training_args,
                train_dataset=train_dataset,
            )

            trainer.train()
            trainer.save_model(training_args.output_dir)
            trainer.push_to_hub(dataset_name=dataset_id)
        case "eval":
            import os
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer

            n_samples = 8
            adapter = adapter or output_dir
            test_dataset = test_dataset.map(make_conversation)

            tokenizer = AutoTokenizer.from_pretrained(model_id, padding_side="left")
            model = AutoModelForCausalLM.from_pretrained(
                model_id, dtype=torch.float16, device_map="auto"
            )
            prompts = [
                tokenizer.apply_chat_template(
                    p, add_generation_prompt=True, tokenize=False
                )
                for p in test_dataset["prompt"]
            ]
            inputs = tokenizer(prompts, return_tensors="pt", padding=True).to(
                model.device
            )
            solutions = [s for s in test_dataset["solution"] for _ in range(n_samples)]

            def evaluate(name):
                torch.manual_seed(0)
                with torch.no_grad():
                    out = model.generate(
                        **inputs,
                        max_new_tokens=512,
                        do_sample=True,
                        num_return_sequences=n_samples,
                    )
                texts = tokenizer.batch_decode(
                    out[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True
                )
                completions = [[{"role": "assistant", "content": t}] for t in texts]
                fmt = format_reward(completions)
                acc = accuracy_reward(completions, solution=solutions)
                print(
                    f"{name}: format {sum(fmt) / len(fmt):.3f}  "
                    f"accuracy {sum(acc) / len(acc):.3f}  (n={len(texts)})"
                )
                print(f"--- {name} sample ---\n{texts[0]}\n")

            if not os.path.exists(os.path.join(adapter, "adapter_config.json")):
                print(f"No adapter at {adapter}, evaluating base model only")
                evaluate("base")
                return
            model = PeftModel.from_pretrained(model, adapter)
            with model.disable_adapter():
                evaluate("base")
            evaluate(f"trained ({adapter})")


ap = argparse.ArgumentParser()
ap.add_argument("--cartpole", default=False, action="store_true")
ap.add_argument("--grpo", default=False, action="store_true")
ap.add_argument("--task", type=str, default="")
ap.add_argument("--adapter", type=str, default="")


def main():
    args = ap.parse_args()
    if args.cartpole:
        cartpole(args.task)

    if args.grpo:
        grpo(args.task, args.adapter)


if __name__ == "__main__":
    main()

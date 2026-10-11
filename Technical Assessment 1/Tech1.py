import agentpy as ap
import random
import matplotlib.pyplot as plt
import matplotlib.animation as animation


# -------------------------------------------------
# Built-in movement settings
# -------------------------------------------------

# Preferred direction: right
PREFERRED_DIRECTION = (1, 0)

# Higher value creates a stronger preference.
PREFERENCE_STRENGTH = 3

# Prevent agents from occupying the same grid cell.
AVOID_OTHER_AGENTS = True


# -------------------------------------------------
# Get user input
# -------------------------------------------------

num_agents = int(input("Enter number of agents: "))
grid_size = int(input("Enter grid size (e.g., 10 for 10x10): "))
num_steps = int(input("Enter number of steps: "))

if num_agents > grid_size ** 2:
    raise ValueError(
        "The number of agents cannot exceed "
        "the number of cells in the grid."
    )


# -------------------------------------------------
# Agent definition
# -------------------------------------------------

class RandomWalker(ap.Agent):

    def setup(self):
        # Store every position visited by this agent.
        self.path = []

    def choose_direction(self):
        directions = [
            (1, 0),   # right
            (-1, 0),  # left
            (0, 1),   # up
            (0, -1)   # down
        ]

        # Add the preferred direction several times.
        # This makes movement to the right more likely.
        movement_choices = (
            directions
            + [PREFERRED_DIRECTION] * PREFERENCE_STRENGTH
        )

        return random.choice(movement_choices)

    def get_next_position(self):
        dx, dy = self.choose_direction()
        x, y = self.position

        new_x = x + dx
        new_y = y + dy

        # Keep the agent inside the grid.
        new_x = max(
            0,
            min(self.model.p.grid_size - 1, new_x)
        )

        new_y = max(
            0,
            min(self.model.p.grid_size - 1, new_y)
        )

        return new_x, new_y


# -------------------------------------------------
# Model definition
# -------------------------------------------------

class RandomWalkModel(ap.Model):

    def setup(self):
        # Create the agents.
        self.agents = ap.AgentList(
            self,
            self.p.agents,
            RandomWalker
        )

        # Create a list containing every grid cell.
        available_cells = [
            (x, y)
            for x in range(self.p.grid_size)
            for y in range(self.p.grid_size)
        ]

        # Give each agent a different starting position.
        starting_positions = random.sample(
            available_cells,
            self.p.agents
        )

        for agent, position in zip(
            self.agents,
            starting_positions
        ):
            agent.position = position
            agent.path.append(position)

    def step(self):
        # Record all currently occupied positions.
        occupied_positions = {
            agent.position for agent in self.agents
        }

        # Randomize which agent moves first.
        movement_order = list(self.agents)
        random.shuffle(movement_order)

        for agent in movement_order:
            current_position = agent.position
            next_position = agent.get_next_position()

            # Temporarily remove the agent's current cell.
            occupied_positions.remove(current_position)

            if (
                not AVOID_OTHER_AGENTS
                or next_position not in occupied_positions
            ):
                # Move if the destination is unoccupied.
                agent.position = next_position
            else:
                # Remain in place if another agent is there.
                agent.position = current_position

            occupied_positions.add(agent.position)

            # Save the latest position in the agent's path.
            agent.path.append(agent.position)


# -------------------------------------------------
# Create the model
# -------------------------------------------------

parameters = {
    "agents": num_agents,
    "grid_size": grid_size
}

model = RandomWalkModel(parameters)
model.setup()


# -------------------------------------------------
# Create the graph
# -------------------------------------------------

fig, ax = plt.subplots(figsize=(8, 8))

ax.set_xlim(-0.5, grid_size - 0.5)
ax.set_ylim(-0.5, grid_size - 0.5)

ax.set_xticks(range(grid_size))
ax.set_yticks(range(grid_size))

ax.grid(True)
ax.set_aspect("equal")

ax.set_xlabel("X position")
ax.set_ylabel("Y position")
ax.set_title("Agent Paths with Rightward Preference")

colors = plt.cm.tab20.colors

# Create one dot and one path line for every agent.
agent_dots = []
agent_lines = []

for index, agent in enumerate(model.agents):
    color = colors[index % len(colors)]

    dot, = ax.plot(
        agent.position[0],
        agent.position[1],
        marker="o",
        markersize=9,
        color=color,
        linestyle="None",
        label=f"Agent {index + 1}"
    )

    path_line, = ax.plot(
        [],
        [],
        color=color,
        linewidth=2,
        alpha=0.75
    )

    agent_dots.append(dot)
    agent_lines.append(path_line)

# Display a legend when the number of agents is manageable.
if num_agents <= 10:
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1))


# -------------------------------------------------
# Animation update
# -------------------------------------------------

def update(frame):
    model.step()

    for index, agent in enumerate(model.agents):
        # Update the agent's current position.
        agent_dots[index].set_data(
            [agent.position[0]],
            [agent.position[1]]
        )

        # Get the complete recorded path.
        x_path = [
            position[0] for position in agent.path
        ]

        y_path = [
            position[1] for position in agent.path
        ]

        # Display the recorded path.
        agent_lines[index].set_data(x_path, y_path)

    ax.set_title(
        "Agent Paths with Rightward Preference\n"
        f"Step {frame + 1} of {num_steps}"
    )

    return agent_dots + agent_lines


simulation_animation = animation.FuncAnimation(
    fig,
    update,
    frames=num_steps,
    interval=500,
    blit=False,
    repeat=False
)

plt.tight_layout()
plt.show()
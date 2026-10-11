# Rule-Based Vacuum Cleaner Agent with Three Rooms


# Ask the user for a valid initial room state.
def get_room_state(room):
    while True:
        state = input(
            f"Enter the initial state of Room {room} "
            "(Dirty or Clean): "
        ).strip().capitalize()

        if state in ["Dirty", "Clean"]:
            return state

        print("Invalid input. Please enter Dirty or Clean.")


# Check whether a room is dirty.
def is_dirty(environment, room):
    return environment[room] == "Dirty"


# Clean the selected room.
def clean_room(environment, room):
    environment[room] = "Clean"


# Rule-based vacuum cleaner agent.
class RuleBasedAgent:

    def __init__(self):
        # The agent starts in Room A.
        self.location = "A"

    def move(self):
        # Move through the rooms in this order:
        # A -> B -> C -> A
        if self.location == "A":
            self.location = "B"
        elif self.location == "B":
            self.location = "C"
        else:
            self.location = "A"

    def perceive_and_act(self, environment):
        # Rule 1:
        # If the current room is dirty, clean it.
        if is_dirty(environment, self.location):
            room_cleaned = self.location
            clean_room(environment, room_cleaned)

            return f"Cleaned Room {room_cleaned}"

        # Rule 2:
        # If the current room is clean, move to the next room.
        previous_location = self.location
        self.move()

        return (
            f"Moved from Room {previous_location} "
            f"to Room {self.location}"
        )


# Set up the three-room environment.
environment = {
    "A": get_room_state("A"),
    "B": get_room_state("B"),
    "C": get_room_state("C")
}

# Create the agent.
agent = RuleBasedAgent()


# Ask for a valid number of simulation steps.
while True:
    try:
        number_of_steps = int(
            input("Enter the number of simulation steps: ")
        )

        if number_of_steps > 0:
            break

        print("Please enter a number greater than zero.")

    except ValueError:
        print("Please enter a valid whole number.")


# Display the initial state.
print("\nInitial Environment")
print(f"Agent Location: Room {agent.location}")
print(f"Room A: {environment['A']}")
print(f"Room B: {environment['B']}")
print(f"Room C: {environment['C']}")


# Run the simulation.
for step in range(1, number_of_steps + 1):
    action = agent.perceive_and_act(environment)

    print(f"\nStep {step}")
    print(f"Action: {action}")
    print(f"Current Location: Room {agent.location}")
    print(
        "Environment: "
        f"Room A = {environment['A']}, "
        f"Room B = {environment['B']}, "
        f"Room C = {environment['C']}"
    )


# Display the final result.
print("\nSimulation Complete")
print(f"Final Agent Location: Room {agent.location}")
print(
    "Final Environment: "
    f"Room A = {environment['A']}, "
    f"Room B = {environment['B']}, "
    f"Room C = {environment['C']}"
)
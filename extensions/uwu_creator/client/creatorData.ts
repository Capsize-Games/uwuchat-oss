export const EMOJI_OPTIONS = [
  "😊", "😎", "🤓", "😏", "🥰", "😤", "🥺", "😴", "🤩", "😭",
  "🫶", "😋", "🤭", "😌", "😜", "🫡", "😇", "🥳", "😈", "👻",
  "🐱", "🦊", "🐶", "🐰", "🐼", "🐸", "🦁", "🐯", "🐺", "🦋",
  "🐝", "🦄", "🦅", "🐉", "🦀", "🐙", "🦎", "🦝", "🦔", "🐧",
  "🧙", "🧚", "🧛", "🧜", "🧝", "👼", "👺", "👹", "🤖", "👾",
  "🥷", "🧟", "🧌", "🧑‍🎤", "🏴‍☠️", "🎭", "👑", "🧿", "💀", "🌀",
  "🌙", "⭐", "🌸", "🌺", "🔥", "💧", "🌊", "⚡", "🌿", "🍀",
  "🌈", "❄️", "✨", "🪐", "🌋", "🍄", "🫧", "🌑", "☁️", "🌪️",
];

export interface Option {
  value: string;
  label: string;
  description?: string;
  emoji?: string;
}

export const GENDER_OPTIONS: Option[] = [
  { value: "Female",      label: "Female",      description: "She / Her",             emoji: "♀️" },
  { value: "Male",        label: "Male",        description: "He / Him",              emoji: "♂️" },
  { value: "Non-binary",  label: "Non-binary",  description: "They / Them",           emoji: "⚧️" },
  { value: "Genderfluid", label: "Genderfluid", description: "Shifts between genders", emoji: "🌊" },
  { value: "Agender",     label: "Agender",     description: "No gender identity",    emoji: "🌑" },
];

export const PERSONALITY_OPTIONS: Option[] = [
  { value: "Sweet & Nurturing",    label: "Sweet & Nurturing",    description: "Warm, caring, always there for you",          emoji: "🥰" },
  { value: "Bold & Adventurous",   label: "Bold & Adventurous",   description: "Fearless, daring, loves a challenge",         emoji: "🤠" },
  { value: "Mysterious & Brooding",label: "Mysterious & Brooding",description: "Quiet depths, hidden secrets",                emoji: "😏" },
  { value: "Playful & Mischievous",label: "Playful & Mischievous",description: "Never misses a chance for a prank",           emoji: "😜" },
  { value: "Intellectual & Bookish",label:"Intellectual & Bookish",description: "Always reading, always thinking",            emoji: "🤓" },
  { value: "Chaotic & Free-spirited",label:"Chaotic & Free-spirited",description:"Unpredictable and impossible to contain",   emoji: "🤪" },
  { value: "Gentle & Shy",         label: "Gentle & Shy",         description: "Soft-spoken, kind at their core",            emoji: "😊" },
  { value: "Passionate & Intense", label: "Passionate & Intense", description: "Feels everything deeply",                    emoji: "😤" },
  { value: "Cool & Laid-back",     label: "Cool & Laid-back",     description: "Unrattled, effortlessly chill",              emoji: "😎" },
  { value: "Dramatic & Theatrical",label: "Dramatic & Theatrical",description: "Every moment deserves a stage",              emoji: "😱" },
  { value: "Sarcastic & Witty",    label: "Sarcastic & Witty",    description: "Sharp tongue, sharper mind",                 emoji: "🙄" },
  { value: "Optimistic & Bubbly",  label: "Optimistic & Bubbly",  description: "Sunshine and good vibes only",               emoji: "😄" },
  { value: "Melancholic & Poetic", label: "Melancholic & Poetic", description: "Finds beauty in sadness",                    emoji: "😔" },
  { value: "Fierce & Protective",  label: "Fierce & Protective",  description: "Loyal to a fault, dangerous when provoked",  emoji: "😡" },
  { value: "Tsundere",             label: "Tsundere",             description: "Tough outside, soft within",                 emoji: "😳" },
  { value: "Kuudere",              label: "Kuudere",              description: "Cold exterior, secretly caring",             emoji: "😐" },
  { value: "Genki",                label: "Genki",                description: "Boundlessly energetic and enthusiastic",     emoji: "🤩" },
  { value: "Yandere",              label: "Yandere",              description: "Dangerously devoted to the ones they love",  emoji: "😈" },
  { value: "Dandere",              label: "Dandere",              description: "Quiet but deeply expressive",                emoji: "🤭" },
  { value: "Trickster",            label: "Trickster",            description: "Chaos agent with a hidden heart of gold",    emoji: "😋" },
  { value: "Stoic Guardian",       label: "Stoic Guardian",       description: "Silent protector who acts when it counts",   emoji: "😑" },
  { value: "Whimsical Dreamer",    label: "Whimsical Dreamer",    description: "Head in clouds, heart in the stars",         emoji: "😶‍🌫️" },
];

export type StepId =
  | "emoji"
  | "gender"
  | "personality"
  | "location"
  | "species"
  | "language"
  | "compose";

export function getVisibleSteps(): StepId[] {
  return [
    "emoji", "gender", "personality",
    "location", "species", "language", "compose",
  ];
}

export const SPECIES_TYPES: Option[] = [
  { value: "human",    label: "Human",    emoji: "👤",
    description: "An ordinary person" },
  { value: "animal",   label: "Animal",   emoji: "🐾",
    description: "A talking animal — frog, cat, fox…" },
  { value: "monster",  label: "Monster",  emoji: "👹",
    description: "Dark, edgy — vampire, ghost, dragon…" },
  { value: "mythical", label: "Mythical", emoji: "🦄",
    description: "Magical, whimsical — fairy, unicorn, phoenix…" },
  { value: "robot",    label: "Robot",    emoji: "🤖",
    description: "Mechanical — android, drone, AI hologram…" },
];

export const SPECIES_SUBTYPES: Record<string, string[]> = {
  animal: [
    "frog", "cat", "dog", "wolf", "fox", "rabbit", "bear",
    "raccoon", "owl", "penguin", "deer", "otter", "axolotl",
    "dragonfly", "turtle", "crow", "hedgehog", "bat",
    "koala", "red panda", "seal", "hamster", "capybara",
  ],
  monster: [
    "dragon", "ghost", "vampire", "werewolf", "demon",
    "slime", "goblin", "kraken", "banshee", "eldritch horror",
    "gargoyle", "lich", "wendigo", "oni", "chimera",
    "zombie", "shade", "nightmare", "harpy", "ogre",
  ],
  mythical: [
    "unicorn", "fairy", "mermaid", "phoenix", "centaur",
    "griffin", "pegasus", "dryad", "kitsune", "sphinx",
    "naga", "sylph", "satyr", "kelpie", "valkyrie",
    "djinn", "pixie", "yokai", "selkie", "leprachaun",
  ],
  robot: [
    "android", "cyborg", "AI hologram", "clockwork automaton",
    "drone", "mecha", "nanite swarm", "industrial bot",
    "companion droid", "sentient starship", "battle mech",
    "service unit", "quantum construct", "steam automaton",
  ],
};

export function pickRandom<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

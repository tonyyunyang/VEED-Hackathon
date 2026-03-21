export interface Van {
    id: string;
    name: string;
    price: number;
    description: string;
    imageUrl: string;
    type: string;
    hostId: string;
}

export interface User {
    id: string;
    email: string;
    name: string;
    password?: string;
    vans?: Van[];
}

export interface Review {
    id: string;
    rating: number;
    name: string;
    date: string;
    text: string;
    hostId: string;
}

export interface Transaction {
    id: string;
    amount: number;
    date: string;
    hostId: string;
}

export interface HostVanInfoContextType {
    photos: { imageUrl: string }[];
    details: {
        name: string | undefined;
        category: string | undefined;
        description: string | undefined;
    };
    pricing: {
        price: number | undefined;
        freq: string;
    };
}

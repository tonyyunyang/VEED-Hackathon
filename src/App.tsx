import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./App.css";
import "./index.css";

import { VideoPlayer } from "./components/VideoPlayer";

function Home() {
  return <VideoPlayer />;
}

function App() {
  return (
    <div className="w-full min-h-screen bg-background font-sans">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />

          <Route
            path="*"
            element={
              <div className="flex h-screen items-center justify-center bg-background text-foreground">
                <h1 className="text-4xl font-bold">404 - Reality not found</h1>
              </div>
            }
          />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;

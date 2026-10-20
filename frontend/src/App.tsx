import { Routes, Route } from "react-router-dom";
import { TopBar } from "./components/TopBar";
import { Home } from "./components/Home";
import { Studio } from "./components/Studio";

export default function App() {
  return (
    <div className="app">
      <TopBar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/studio/:id" element={<Studio />} />
      </Routes>
    </div>
  );
}

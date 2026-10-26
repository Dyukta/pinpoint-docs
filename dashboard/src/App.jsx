import Chat from "./Chat";

export default function App() {
  return (
    <div className="flex h-screen justify-center p-4 font-sans text-white sm:p-8">
      <div className="flex w-full max-w-3xl flex-col rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl">
        <h1 className="border-b border-zinc-800 px-5 py-4 text-lg font-semibold">
          Pinpoint<span className="text-red-500">.</span>
        </h1>
        <Chat />
      </div>
    </div>
  );
}

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { SecurityEvents } from "../components/SecurityEvents";
import { SecurityAlerts } from "../components/SecurityAlerts";
import { SecurityRules } from "../components/SecurityRules";

export function SecurityPage() {
  const [activeTab, setActiveTab] = useState("events");

  return (
    <div className="h-full w-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b border-border bg-card px-6 py-4">
        <h1 className="text-2xl font-bold text-foreground">
          Мониторинг безопасности
        </h1>
      </div>

      {/* Tabs */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <div className="border-b border-border bg-card px-6">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList>
              <TabsTrigger value="events">События</TabsTrigger>
              <TabsTrigger value="alerts">Алерты</TabsTrigger>
              <TabsTrigger value="rules">Правила</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          <div className="p-6">
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsContent value="events">
                <SecurityEvents />
              </TabsContent>
              <TabsContent value="alerts">
                <SecurityAlerts />
              </TabsContent>
              <TabsContent value="rules">
                <SecurityRules />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
}
